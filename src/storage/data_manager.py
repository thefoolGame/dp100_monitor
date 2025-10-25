"""Data storage manager for DP100 Monitor."""

import h5py
import pandas as pd
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from queue import Queue, Empty

from .data_models import PowerMeasurement, SessionInfo
from ..utils.logger import get_logger


class DataManager:
    """Manages data storage for power measurements."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize data manager.

        Args:
            config: Application configuration
        """
        self.config = config["storage"]
        self.logger = get_logger("storage")

        # Ensure data directories exist
        self.sessions_dir = Path("data/sessions")
        self.exports_dir = Path("data/exports")
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.exports_dir.mkdir(parents=True, exist_ok=True)

        # Storage state
        self.current_session: Optional[SessionInfo] = None
        self.hdf5_file: Optional[h5py.File] = None
        self.write_queue: Queue = Queue()
        self.running = False
        self.writer_thread: Optional[threading.Thread] = None

        # Buffer for batch writing
        self.write_buffer: List[PowerMeasurement] = []
        self.buffer_size = self.config.get("buffer_size", 1000)

    def start_session(self, session_id: Optional[str] = None) -> SessionInfo:
        """
        Start a new data collection session.

        Args:
            session_id: Optional session identifier

        Returns:
            Session information
        """
        if self.current_session:
            self.end_session()

        session_id = session_id or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.current_session = SessionInfo(session_id, datetime.now())

        # Setup file paths
        self.current_session.file_path = str(self.sessions_dir / f"{session_id}.h5")
        self.current_session.backup_path = str(
            self.exports_dir / f"session_{session_id}.csv"
        )

        # Create HDF5 file
        try:
            self.hdf5_file = h5py.File(self.current_session.file_path, "w")
            # Create datasets with chunking for efficient appending
            dataset_kwargs = {
                "chunks": (min(1000, self.buffer_size),),
                "maxshape": (None,),
            }
            self.hdf5_file.create_dataset(
                "timestamp", (0,), dtype="S26", **dataset_kwargs
            )
            self.hdf5_file.create_dataset("voltage", (0,), dtype="f8", **dataset_kwargs)
            self.hdf5_file.create_dataset("current", (0,), dtype="f8", **dataset_kwargs)
            self.hdf5_file.create_dataset("power", (0,), dtype="f8", **dataset_kwargs)

            # Add metadata
            self.hdf5_file.attrs["session_id"] = session_id
            self.hdf5_file.attrs["start_time"] = (
                self.current_session.start_time.isoformat()
            )

        except Exception as e:
            self.logger.error(f"Failed to create HDF5 file: {e}")
            raise

        # Start writer thread
        self.running = True
        self.writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self.writer_thread.start()

        self.logger.info(f"Started session: {session_id}")
        return self.current_session

    def end_session(self) -> None:
        """End current data collection session."""
        if not self.current_session:
            return

        self.running = False
        if self.writer_thread:
            self.writer_thread.join(timeout=5.0)

        self._flush_buffer()  # Flush any remaining data

        if self.hdf5_file:
            try:
                self.current_session.end_time = datetime.now()
                self.hdf5_file.attrs["end_time"] = (
                    self.current_session.end_time.isoformat()
                )
                self.hdf5_file.attrs["sample_count"] = self.current_session.sample_count
                self.hdf5_file.close()
            except Exception as e:
                self.logger.error(f"Error closing HDF5 file: {e}")
            finally:
                self.hdf5_file = None

        # Export final CSV from the HDF5 file
        if self.current_session.sample_count > 0:
            self._export_csv()

        self.logger.info(
            f"Ended session: {self.current_session.session_id} ({self.current_session.sample_count} samples)"
        )
        self.current_session = None

    def add_measurement(self, measurement: PowerMeasurement) -> None:
        """Add measurement to storage queue."""
        if not self.running:
            return
        try:
            self.write_queue.put_nowait(measurement)
        except Exception as e:
            self.logger.error(f"Failed to queue measurement: {e}")

    def _writer_loop(self) -> None:
        """Background thread for writing data."""
        while self.running:
            try:
                measurement = self.write_queue.get(timeout=1.0)
                self.write_buffer.append(measurement)
                if len(self.write_buffer) >= self.buffer_size:
                    self._flush_buffer()
            except Empty:
                continue  # This is expected when the queue is empty
            except Exception as e:
                self.logger.error(f"Error in writer loop: {e}")

    def _flush_buffer(self) -> None:
        """Flush write buffer to HDF5 file."""
        if not self.write_buffer or not self.hdf5_file:
            return

        try:
            count = len(self.write_buffer)
            timestamps = [
                m.timestamp.isoformat().encode("utf-8") for m in self.write_buffer
            ]
            voltages = [m.voltage for m in self.write_buffer]
            currents = [m.current for m in self.write_buffer]
            powers = [m.power for m in self.write_buffer]

            current_size = self.hdf5_file["timestamp"].shape[0]
            new_size = current_size + count

            for key in ["timestamp", "voltage", "current", "power"]:
                self.hdf5_file[key].resize((new_size,))

            self.hdf5_file["timestamp"][current_size:new_size] = timestamps
            self.hdf5_file["voltage"][current_size:new_size] = voltages
            self.hdf5_file["current"][current_size:new_size] = currents
            self.hdf5_file["power"][current_size:new_size] = powers

            self.hdf5_file.flush()
            if self.current_session:
                self.current_session.sample_count += count
            self.logger.debug(f"Flushed {count} measurements to HDF5")
        except Exception as e:
            self.logger.error(f"Error flushing buffer: {e}")
        finally:
            self.write_buffer.clear()

    def _export_csv(self) -> None:
        """Export final session data to CSV from the HDF5 file."""
        if not self.current_session or not self.current_session.backup_path:
            return

        try:
            with h5py.File(self.current_session.file_path, "r") as f:
                df = pd.DataFrame(
                    {
                        "timestamp": pd.to_datetime(
                            [ts.decode("utf-8") for ts in f["timestamp"][:]]
                        ),
                        "voltage": f["voltage"][:],
                        "current": f["current"][:],
                        "power": f["power"][:],
                    }
                )
            df.to_csv(self.current_session.backup_path, index=False)
            self.logger.info(
                f"Exported session to CSV: {self.current_session.backup_path}"
            )
        except Exception as e:
            self.logger.error(f"Error exporting CSV: {e}")
