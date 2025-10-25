"""Data models and structures for DP100 Monitor."""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
import pandas as pd


@dataclass
class PowerMeasurement:
    """Single power measurement from DP100."""

    timestamp: datetime
    voltage: float  # Volts
    current: float  # Amperes
    power: float  # Watts (calculated)

    def __post_init__(self):
        """Calculate power if not provided."""
        if self.power == 0.0:
            self.power = self.voltage * self.current

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "voltage": self.voltage,
            "current": self.current,
            "power": self.power,
        }


class MeasurementBuffer:
    """Circular buffer for power measurements."""

    def __init__(self, max_size: int = 5000):
        """
        Initialize measurement buffer.

        Args:
            max_size: Maximum number of measurements to store
        """
        self.max_size = max_size
        self.measurements: List[PowerMeasurement] = []
        self._index = 0
        self._full = False

    def add(self, measurement: PowerMeasurement) -> None:
        """
        Add measurement to buffer.

        Args:
            measurement: Power measurement to add
        """
        if len(self.measurements) < self.max_size:
            self.measurements.append(measurement)
        else:
            # Circular buffer behavior
            self.measurements[self._index] = measurement
            self._index = (self._index + 1) % self.max_size
            self._full = True

    def get_recent(self, count: Optional[int] = None) -> List[PowerMeasurement]:
        """
        Get recent measurements.

        Args:
            count: Number of recent measurements to return (None for all)

        Returns:
            List of recent measurements
        """
        if not self.measurements:
            return []

        if not self._full:
            # Buffer not full yet, return in order
            recent = self.measurements
        else:
            # Buffer is full, need to reorder
            recent = self.measurements[self._index :] + self.measurements[: self._index]

        if count is not None:
            recent = recent[-count:]

        return recent

    def to_dataframe(self, count: Optional[int] = None) -> pd.DataFrame:
        """
        Convert recent measurements to pandas DataFrame.

        Args:
            count: Number of recent measurements to include

        Returns:
            DataFrame with measurements
        """
        measurements = self.get_recent(count)

        if not measurements:
            return pd.DataFrame(columns=["timestamp", "voltage", "current", "power"])

        data = [m.to_dict() for m in measurements]
        df = pd.DataFrame(data)
        df.set_index("timestamp", inplace=True)
        return df

    def clear(self) -> None:
        """Clear all measurements from buffer."""
        self.measurements.clear()
        self._index = 0
        self._full = False

    def __len__(self) -> int:
        """Return number of measurements in buffer."""
        return len(self.measurements)

    def is_full(self) -> bool:
        """Check if buffer is full."""
        return self._full


class SessionInfo:
    """Information about a data collection session."""

    def __init__(self, session_id: str, start_time: datetime):
        """
        Initialize session info.

        Args:
            session_id: Unique session identifier
            start_time: Session start time
        """
        self.session_id = session_id
        self.start_time = start_time
        self.end_time: Optional[datetime] = None
        self.sample_count = 0
        self.file_path: Optional[str] = None
        self.backup_path: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "sample_count": self.sample_count,
            "file_path": self.file_path,
            "backup_path": self.backup_path,
        }
