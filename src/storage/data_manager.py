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
        self.config = config['storage']
        self.logger = get_logger('storage')
        
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
        self.buffer_size = self.config.get('buffer_size', 1000)
        self.backup_interval = self.config.get('backup_interval', 1000)
        self.samples_since_backup = 0
    
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
        
        # Generate session ID if not provided
        if session_id is None:
            session_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        # Create session info
        self.current_session = SessionInfo(session_id, datetime.now())
        
        # Setup file paths
        hdf5_filename = f"{session_id}.h5"
        self.current_session.file_path = str(self.sessions_dir / hdf5_filename)
        
        csv_filename = f"session_{session_id}.csv"
        self.current_session.backup_path = str(self.exports_dir / csv_filename)
        
        # Create HDF5 file
        try:
            self.hdf5_file = h5py.File(self.current_session.file_path, 'w')
            
            # Create datasets with compression
            compression = self.config.get('compression', None)
            compression_level = self.config.get('compression_level', 1)
            
            # Check if compression should be used and is available
            use_compression = False
            if compression is not None:
                try:
                    # Test compression availability
                    h5py.h5z.filter_avail(h5py.h5z.FILTER_DEFLATE)
                    use_compression = True
                except:
                    self.logger.warning(f"Compression '{compression}' not available, disabling compression")
                    compression = None
                    use_compression = False
            
            # Create datasets with initial size and chunking for efficient appending
            chunk_size = min(1000, self.buffer_size)
            
            # Prepare dataset creation arguments
            dataset_kwargs = {
                'dtype': 'S26',
                'chunks': (chunk_size,),
                'maxshape': (None,)
            }
            if use_compression:
                dataset_kwargs.update({
                    'compression': compression,
                    'compression_opts': compression_level
                })
            
            self.hdf5_file.create_dataset('timestamp', (0,), **dataset_kwargs)
            
            # Update kwargs for numeric datasets
            dataset_kwargs['dtype'] = 'f8'
            
            self.hdf5_file.create_dataset('voltage', (0,), **dataset_kwargs)
            self.hdf5_file.create_dataset('current', (0,), **dataset_kwargs)
            self.hdf5_file.create_dataset('power', (0,), **dataset_kwargs)
            
            # Add metadata
            self.hdf5_file.attrs['session_id'] = session_id
            self.hdf5_file.attrs['start_time'] = self.current_session.start_time.isoformat()
            self.hdf5_file.attrs['sampling_rate'] = self.config.get('sampling_rate', 50)
            
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
        
        # Stop writer thread
        self.running = False
        if self.writer_thread:
            self.writer_thread.join(timeout=5.0)
        
        # Flush any remaining data
        self._flush_buffer()
        
        # Close HDF5 file
        if self.hdf5_file:
            try:
                self.current_session.end_time = datetime.now()
                self.hdf5_file.attrs['end_time'] = self.current_session.end_time.isoformat()
                self.hdf5_file.attrs['sample_count'] = self.current_session.sample_count
                self.hdf5_file.close()
            except Exception as e:
                self.logger.error(f"Error closing HDF5 file: {e}")
            finally:
                self.hdf5_file = None
        
        # Export final CSV
        if self.current_session.sample_count > 0:
            self._export_csv()
        
        self.logger.info(f"Ended session: {self.current_session.session_id} "
                        f"({self.current_session.sample_count} samples)")
        
        self.current_session = None
        self.write_buffer.clear()
        self.samples_since_backup = 0
    
    def add_measurement(self, measurement: PowerMeasurement) -> None:
        """
        Add measurement to storage queue.
        
        Args:
            measurement: Power measurement to store
        """
        if not self.current_session:
            return
        
        try:
            self.write_queue.put_nowait(measurement)
        except Exception as e:
            self.logger.error(f"Failed to queue measurement: {e}")
    
    def _writer_loop(self) -> None:
        """Background thread for writing data."""
        while self.running:
            try:
                # Get measurement from queue with timeout
                try:
                    measurement = self.write_queue.get(timeout=1.0)
                except Empty:
                    continue
                
                # Add to buffer
                self.write_buffer.append(measurement)
                
                # Write buffer if full
                if len(self.write_buffer) >= self.buffer_size:
                    self._flush_buffer()
                
                # Periodic CSV backup
                self.samples_since_backup += 1
                if self.samples_since_backup >= self.backup_interval:
                    self._backup_csv()
                    self.samples_since_backup = 0
                
            except Exception as e:
                self.logger.error(f"Error in writer loop: {e}")
    
    def _flush_buffer(self) -> None:
        """Flush write buffer to HDF5 file."""
        if not self.write_buffer or not self.hdf5_file:
            return
        
        try:
            # Prepare data arrays
            timestamps = [m.timestamp.isoformat().encode('utf-8') for m in self.write_buffer]
            voltages = [m.voltage for m in self.write_buffer]
            currents = [m.current for m in self.write_buffer]
            powers = [m.power for m in self.write_buffer]
            
            # Get current dataset size
            current_size = self.hdf5_file['timestamp'].shape[0]
            new_size = current_size + len(self.write_buffer)
            
            # Resize datasets
            self.hdf5_file['timestamp'].resize((new_size,))
            self.hdf5_file['voltage'].resize((new_size,))
            self.hdf5_file['current'].resize((new_size,))
            self.hdf5_file['power'].resize((new_size,))
            
            # Write data
            self.hdf5_file['timestamp'][current_size:new_size] = timestamps
            self.hdf5_file['voltage'][current_size:new_size] = voltages
            self.hdf5_file['current'][current_size:new_size] = currents
            self.hdf5_file['power'][current_size:new_size] = powers
            
            # Flush to disk
            self.hdf5_file.flush()
            
            # Update session info
            if self.current_session:
                self.current_session.sample_count += len(self.write_buffer)
            
            self.logger.debug(f"Flushed {len(self.write_buffer)} measurements to HDF5")
            
        except Exception as e:
            self.logger.error(f"Error flushing buffer: {e}")
        finally:
            self.write_buffer.clear()
    
    def _backup_csv(self) -> None:
        """Create CSV backup of current data."""
        if not self.current_session or not self.hdf5_file:
            return
        
        try:
            # Read all data from HDF5
            timestamps = [ts.decode('utf-8') for ts in self.hdf5_file['timestamp'][:]]
            voltages = self.hdf5_file['voltage'][:]
            currents = self.hdf5_file['current'][:]
            powers = self.hdf5_file['power'][:]
            
            # Create DataFrame
            df = pd.DataFrame({
                'timestamp': pd.to_datetime(timestamps),
                'voltage': voltages,
                'current': currents,
                'power': powers
            })
            
            # Write to CSV
            backup_path = self.exports_dir / "backup_partial.csv"
            df.to_csv(backup_path, index=False)
            
            self.logger.debug(f"Created CSV backup with {len(df)} samples")
            
        except Exception as e:
            self.logger.error(f"Error creating CSV backup: {e}")
    
    def _export_csv(self) -> None:
        """Export final session data to CSV."""
        if not self.current_session or not self.current_session.backup_path:
            return
        
        try:
            # Read all data from HDF5
            with h5py.File(self.current_session.file_path, 'r') as f:
                timestamps = [ts.decode('utf-8') for ts in f['timestamp'][:]]
                voltages = f['voltage'][:]
                currents = f['current'][:]
                powers = f['power'][:]
            
            # Create DataFrame
            df = pd.DataFrame({
                'timestamp': pd.to_datetime(timestamps),
                'voltage': voltages,
                'current': currents,
                'power': powers
            })
            
            # Write to final CSV
            df.to_csv(self.current_session.backup_path, index=False)
            
            self.logger.info(f"Exported session to CSV: {self.current_session.backup_path}")
            
        except Exception as e:
            self.logger.error(f"Error exporting CSV: {e}")
    
    def get_session_data(self, session_path: str, 
                        start_time: Optional[datetime] = None,
                        end_time: Optional[datetime] = None) -> pd.DataFrame:
        """
        Load session data from file.
        
        Args:
            session_path: Path to session HDF5 file
            start_time: Optional start time filter
            end_time: Optional end time filter
            
        Returns:
            DataFrame with session data
        """
        try:
            with h5py.File(session_path, 'r') as f:
                timestamps = [ts.decode('utf-8') for ts in f['timestamp'][:]]
                voltages = f['voltage'][:]
                currents = f['current'][:]
                powers = f['power'][:]
            
            df = pd.DataFrame({
                'timestamp': pd.to_datetime(timestamps),
                'voltage': voltages,
                'current': currents,
                'power': powers
            })
            
            # Apply time filters
            if start_time:
                df = df[df['timestamp'] >= start_time]
            if end_time:
                df = df[df['timestamp'] <= end_time]
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error loading session data: {e}")
            return pd.DataFrame()
    
    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        List available sessions.
        
        Returns:
            List of session information dictionaries
        """
        sessions = []
        
        for hdf5_file in self.sessions_dir.glob("*.h5"):
            try:
                with h5py.File(hdf5_file, 'r') as f:
                    session_info = {
                        'file_path': str(hdf5_file),
                        'session_id': f.attrs.get('session_id', ''),
                        'start_time': f.attrs.get('start_time', ''),
                        'end_time': f.attrs.get('end_time', ''),
                        'sample_count': f.attrs.get('sample_count', 0),
                        'file_size_mb': hdf5_file.stat().st_size / 1024 / 1024
                    }
                    sessions.append(session_info)
            except Exception as e:
                self.logger.warning(f"Could not read session file {hdf5_file}: {e}")
        
        return sorted(sessions, key=lambda x: x['start_time'], reverse=True)