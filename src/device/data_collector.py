"""High-frequency data collection thread for DP100."""

import threading
import time
import queue
from datetime import datetime
from typing import Dict, Any, Optional, Callable

from .dp100_interface import DP100Interface
from ..storage.data_models import PowerMeasurement
from ..utils.logger import get_logger


class DataCollector:
    """High-frequency data collection from DP100."""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize data collector.

        Args:
            config: Application configuration
        """
        self.config = config
        self.logger = get_logger("device.collector")

        # DP100 interface
        self.dp100 = DP100Interface(config)

        # Collection settings
        self.sampling_rate = config["device"]["sampling_rate"]
        self.sample_interval = 1.0 / self.sampling_rate

        # Threading
        self.running = False
        self.collection_thread: Optional[threading.Thread] = None

        # Data output
        self.data_queue: queue.Queue = queue.Queue(maxsize=1000)

        # Callbacks
        self.error_callback: Optional[Callable[[str], None]] = None
        self.status_callback: Optional[Callable[[Dict[str, Any]], None]] = None

        # Statistics
        self.stats = {
            "samples_collected": 0,
            "samples_per_second": 0.0,
            "errors": 0,
            "last_sample_time": None,
            "collection_start_time": None,
            "missed_samples": 0,
        }

        # Timing tracking
        self._last_collection_time = 0.0
        self._sample_times = []
        self._stats_update_time = 0.0

    def start(self) -> bool:
        """
        Start data collection.

        Returns:
            True if started successfully
        """
        if self.running:
            self.logger.warning("Data collection already running")
            return True

        # Connect to DP100
        if not self.dp100.connect():
            self.logger.error("Failed to connect to DP100")
            return False

        # Reset statistics
        self._reset_stats()

        # Start collection thread
        self.running = True
        self.collection_thread = threading.Thread(
            target=self._collection_loop, daemon=True
        )
        self.collection_thread.start()

        self.logger.info(f"Started data collection at {self.sampling_rate} Hz")
        return True

    def stop(self) -> None:
        """Stop data collection."""
        if not self.running:
            return

        self.running = False

        # Wait for thread to finish
        if self.collection_thread:
            self.collection_thread.join(timeout=2.0)
            if self.collection_thread.is_alive():
                self.logger.warning("Collection thread did not stop gracefully")

        # Keep device connected - just stop collection
        # self.dp100.disconnect()  # Don't disconnect, keep for manual control

        # Log final statistics
        duration = time.time() - self.stats["collection_start_time"]
        self.logger.info(
            f"Stopped data collection. "
            f"Collected {self.stats['samples_collected']} samples "
            f"in {duration:.1f}s "
            f"({self.stats['samples_collected']/duration:.1f} avg Hz)"
        )

    def _collection_loop(self) -> None:
        """Main data collection loop."""
        self.logger.debug("Collection loop started")

        next_sample_time = time.time()

        while self.running:
            current_time = time.time()

            # Check if it's time for next sample
            if current_time >= next_sample_time:
                self._collect_sample(current_time)

                # Calculate next sample time
                next_sample_time += self.sample_interval

                # Check for missed samples
                if current_time > next_sample_time:
                    missed = int(
                        (current_time - next_sample_time) / self.sample_interval
                    )
                    if missed > 0:
                        self.stats["missed_samples"] += missed
                        self.logger.warning(f"Missed {missed} samples due to timing")
                        next_sample_time = current_time + self.sample_interval

            # Update statistics periodically
            if current_time - self._stats_update_time >= 1.0:
                self._update_statistics()
                self._stats_update_time = current_time

            # Small sleep to prevent busy waiting
            sleep_time = max(0.001, next_sample_time - time.time())
            time.sleep(min(sleep_time, 0.001))

    def _collect_sample(self, timestamp_seconds: float) -> None:
        """
        Collect a single sample.

        Args:
            timestamp_seconds: Unix timestamp for the sample
        """
        try:
            # Get measurement from DP100
            measurement_data = self.dp100.get_measurement()

            if measurement_data is None:
                self.stats["errors"] += 1
                self._handle_error("Failed to get measurement from DP100")
                return

            voltage, current, power = measurement_data

            # Create measurement object
            measurement = PowerMeasurement(
                timestamp=datetime.fromtimestamp(timestamp_seconds),
                voltage=voltage,
                current=current,
                power=power,
            )

            # Add to queue (non-blocking)
            try:
                self.data_queue.put_nowait(measurement)
            except queue.Full:
                self.logger.warning("Data queue full, dropping sample")
                self.stats["errors"] += 1
                return

            # Update statistics
            self.stats["samples_collected"] += 1
            self.stats["last_sample_time"] = timestamp_seconds
            self._sample_times.append(timestamp_seconds)

            # Keep only recent sample times for rate calculation
            cutoff_time = timestamp_seconds - 1.0
            self._sample_times = [t for t in self._sample_times if t > cutoff_time]

        except Exception as e:
            self.stats["errors"] += 1
            self._handle_error(f"Error collecting sample: {e}")

    def _update_statistics(self) -> None:
        """Update collection statistics."""
        # Calculate samples per second
        if len(self._sample_times) > 1:
            time_span = self._sample_times[-1] - self._sample_times[0]
            if time_span > 0:
                self.stats["samples_per_second"] = len(self._sample_times) / time_span

        # Send status update if callback is set
        if self.status_callback:
            status = {
                "connected": self.dp100.is_connected(),
                "sampling_rate": self.stats["samples_per_second"],
                "target_rate": self.sampling_rate,
                "samples_collected": self.stats["samples_collected"],
                "errors": self.stats["errors"],
                "missed_samples": self.stats["missed_samples"],
                "queue_size": self.data_queue.qsize(),
            }

            try:
                self.status_callback(status)
            except Exception as e:
                self.logger.error(f"Error in status callback: {e}")

    def _handle_error(self, error_message: str) -> None:
        """
        Handle collection errors.

        Args:
            error_message: Error description
        """
        self.logger.error(error_message)

        # Try to reconnect if connection lost
        if not self.dp100.is_connected():
            self.logger.info("Attempting to reconnect...")
            if self.dp100.reconnect():
                self.logger.info("Reconnected successfully")
            else:
                self.logger.error("Reconnection failed")

        # Notify error callback
        if self.error_callback:
            try:
                self.error_callback(error_message)
            except Exception as e:
                self.logger.error(f"Error in error callback: {e}")

    def _reset_stats(self) -> None:
        """Reset collection statistics."""
        current_time = time.time()
        self.stats = {
            "samples_collected": 0,
            "samples_per_second": 0.0,
            "errors": 0,
            "last_sample_time": None,
            "collection_start_time": current_time,
            "missed_samples": 0,
        }
        self._sample_times.clear()
        self._stats_update_time = current_time

        # Clear data queue to prevent plotting old data from previous session
        with self.data_queue.mutex:
            self.data_queue.queue.clear()

    def get_sample(self, timeout: float = 0.1) -> Optional[PowerMeasurement]:
        """
        Get next sample from queue.

        Args:
            timeout: Timeout in seconds

        Returns:
            PowerMeasurement or None if timeout
        """
        try:
            return self.data_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_samples(self, max_count: int = 100) -> list[PowerMeasurement]:
        """
        Get multiple samples from queue.

        Args:
            max_count: Maximum number of samples to retrieve

        Returns:
            List of PowerMeasurement objects
        """
        samples = []

        for _ in range(max_count):
            try:
                sample = self.data_queue.get_nowait()
                samples.append(sample)
            except queue.Empty:
                break

        return samples

    def set_error_callback(self, callback: Callable[[str], None]) -> None:
        """
        Set callback for error notifications.

        Args:
            callback: Function to call on errors
        """
        self.error_callback = callback

    def set_status_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Set callback for status updates.

        Args:
            callback: Function to call with status updates
        """
        self.status_callback = callback

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get current collection statistics.

        Returns:
            Statistics dictionary
        """
        stats = self.stats.copy()
        stats["queue_size"] = self.data_queue.qsize()
        stats["connected"] = self.dp100.is_connected()

        if self.stats["collection_start_time"]:
            stats["runtime_seconds"] = time.time() - self.stats["collection_start_time"]

        return stats

    def is_running(self) -> bool:
        """Check if data collection is running."""
        return self.running

    def get_device_info(self) -> Dict[str, Any]:
        """Get DP100 device information."""
        return self.dp100.get_device_info()

    def get_single_measurement(self) -> Optional[PowerMeasurement]:
        """
        Get a single power measurement from the device.

        This method bypasses the collection loop and queue, directly fetching
        the latest measurement from the DP100 device.

        Returns:
            PowerMeasurement object or None if measurement fails
        """
        try:
            measurement_data = self.dp100.get_measurement()
            if measurement_data:
                voltage, current, power = measurement_data
                return PowerMeasurement(
                    timestamp=datetime.now(),
                    voltage=voltage,
                    current=current,
                    power=power,
                )
            return None
        except Exception as e:
            self.logger.error(f"Error getting single measurement: {e}")
            return None
