"""Real-time plotting component for DP100 Monitor."""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from ...utils.logger import get_logger


class RealtimePlot:
    """Real-time plotting component for power measurements."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize real-time plot.
        
        Args:
            config: Application configuration
        """
        self.config = config['gui']
        self.logger = get_logger('gui.plot')
        
        # Plot settings
        self.plot_window_seconds = self.config.get('plot_window', 60)
        self.decimation_factor = self.config.get('decimation_factor', 5)
        
        # Data buffers for plotting
        self.max_points = int(self.plot_window_seconds * 50 / self.decimation_factor)  # Assume 50Hz max
        self.timestamps = deque(maxlen=self.max_points)
        self.voltages = deque(maxlen=self.max_points)
        self.currents = deque(maxlen=self.max_points)
        self.powers = deque(maxlen=self.max_points)
        
        # Plot counter for decimation
        self.plot_counter = 0
        
        # Statistics
        self.stats = {
            'points_plotted': 0,
            'last_update': None,
            'update_rate': 0.0
        }
    
    def add_data_point(self, timestamp: datetime, voltage: float, 
                      current: float, power: float) -> None:
        """
        Add data point to plot buffers with decimation.
        
        Args:
            timestamp: Measurement timestamp
            voltage: Voltage in volts
            current: Current in amperes
            power: Power in watts
        """
        # Apply decimation
        self.plot_counter += 1
        if self.plot_counter % self.decimation_factor != 0:
            return
        
        # Add to buffers
        self.timestamps.append(timestamp)
        self.voltages.append(voltage)
        self.currents.append(current)
        self.powers.append(power)
        
        # Update statistics
        self.stats['points_plotted'] += 1
        self.stats['last_update'] = timestamp
    
    def add_data_batch(self, measurements: List[Dict[str, Any]]) -> None:
        """
        Add batch of measurements.
        
        Args:
            measurements: List of measurement dictionaries
        """
        for measurement in measurements:
            self.add_data_point(
                measurement['timestamp'],
                measurement['voltage'],
                measurement['current'],
                measurement['power']
            )
    
    def create_figure(self) -> go.Figure:
        """
        Create Plotly figure with current data.
        
        Returns:
            Plotly figure object
        """
        # Create subplots
        fig = make_subplots(
            rows=3, cols=1,
            subplot_titles=('Voltage (V)', 'Current (A)', 'Power (W)'),
            vertical_spacing=0.08,
            shared_xaxes=True
        )
        
        # Convert timestamps to list for plotting
        timestamps_list = list(self.timestamps)
        voltages_list = list(self.voltages)
        currents_list = list(self.currents)
        powers_list = list(self.powers)
        
        # Add voltage trace
        fig.add_trace(
            go.Scatter(
                x=timestamps_list,
                y=voltages_list,
                mode='lines',
                name='Voltage',
                line=dict(color='blue', width=2),
                showlegend=False
            ),
            row=1, col=1
        )
        
        # Add current trace
        fig.add_trace(
            go.Scatter(
                x=timestamps_list,
                y=currents_list,
                mode='lines',
                name='Current',
                line=dict(color='red', width=2),
                showlegend=False
            ),
            row=2, col=1
        )
        
        # Add power trace
        fig.add_trace(
            go.Scatter(
                x=timestamps_list,
                y=powers_list,
                mode='lines',
                name='Power',
                line=dict(color='green', width=2),
                showlegend=False
            ),
            row=3, col=1
        )
        
        # Update layout
        fig.update_layout(
            height=600,
            title="Real-time Power Monitoring",
            title_x=0.5,
            margin=dict(l=60, r=20, t=80, b=60),
            plot_bgcolor='white',
            paper_bgcolor='white'
        )
        
        # Update axes
        fig.update_xaxes(
            showgrid=True, 
            gridwidth=1, 
            gridcolor='lightgray',
            row=3, col=1,
            title_text="Time"
        )
        
        for row in range(1, 4):
            fig.update_yaxes(
                showgrid=True, 
                gridwidth=1, 
                gridcolor='lightgray',
                row=row, col=1
            )
        
        # Set axis ranges if we have data
        if timestamps_list:
            # Set x-axis range to show the last window
            latest_time = timestamps_list[-1]
            start_time = latest_time - timedelta(seconds=self.plot_window_seconds)
            
            fig.update_xaxes(
                range=[start_time, latest_time],
                row=3, col=1
            )
        
        return fig
    
    def get_latest_values(self) -> Dict[str, Optional[float]]:
        """
        Get latest measurement values.
        
        Returns:
            Dictionary with latest values
        """
        if not self.timestamps:
            return {
                'voltage': None,
                'current': None,
                'power': None,
                'timestamp': None
            }
        
        return {
            'voltage': self.voltages[-1],
            'current': self.currents[-1],
            'power': self.powers[-1],
            'timestamp': self.timestamps[-1]
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get plotting statistics.
        
        Returns:
            Statistics dictionary
        """
        stats = self.stats.copy()
        stats['buffer_size'] = len(self.timestamps)
        stats['max_buffer_size'] = self.max_points
        stats['decimation_factor'] = self.decimation_factor
        
        # Calculate update rate
        if len(self.timestamps) >= 2:
            time_span = (self.timestamps[-1] - self.timestamps[0]).total_seconds()
            if time_span > 0:
                stats['update_rate'] = len(self.timestamps) / time_span
        
        return stats
    
    def clear_data(self) -> None:
        """Clear all plot data."""
        self.timestamps.clear()
        self.voltages.clear()
        self.currents.clear()
        self.powers.clear()
        self.plot_counter = 0
        self.stats['points_plotted'] = 0
        self.logger.info("Plot data cleared")
    
    def set_time_window(self, seconds: int) -> None:
        """
        Set plot time window.
        
        Args:
            seconds: Time window in seconds
        """
        self.plot_window_seconds = seconds
        self.max_points = int(seconds * 50 / self.decimation_factor)
        
        # Update buffer sizes
        self.timestamps = deque(self.timestamps, maxlen=self.max_points)
        self.voltages = deque(self.voltages, maxlen=self.max_points)
        self.currents = deque(self.currents, maxlen=self.max_points)
        self.powers = deque(self.powers, maxlen=self.max_points)
        
        self.logger.info(f"Plot time window set to {seconds} seconds")
    
    def set_decimation_factor(self, factor: int) -> None:
        """
        Set decimation factor.
        
        Args:
            factor: Decimation factor (1 = no decimation)
        """
        if factor < 1:
            factor = 1
        
        self.decimation_factor = factor
        self.max_points = int(self.plot_window_seconds * 50 / factor)
        
        # Update buffer sizes
        self.timestamps = deque(self.timestamps, maxlen=self.max_points)
        self.voltages = deque(self.voltages, maxlen=self.max_points)
        self.currents = deque(self.currents, maxlen=self.max_points)
        self.powers = deque(self.powers, maxlen=self.max_points)
        
        self.logger.info(f"Decimation factor set to {factor}")
    
    def export_data(self) -> pd.DataFrame:
        """
        Export current plot data as DataFrame.
        
        Returns:
            DataFrame with plot data
        """
        if not self.timestamps:
            return pd.DataFrame(columns=['timestamp', 'voltage', 'current', 'power'])
        
        df = pd.DataFrame({
            'timestamp': list(self.timestamps),
            'voltage': list(self.voltages),
            'current': list(self.currents),
            'power': list(self.powers)
        })
        
        return df