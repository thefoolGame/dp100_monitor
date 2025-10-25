"""Main dashboard for DP100 Monitor."""

import dash
from dash import html, dcc, Input, Output, State, callback_context
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional

from .components.realtime_plot import RealtimePlot
from .components.controls import ControlPanel, create_alerts_container, create_alert, create_statistics_display, format_statistics, create_energy_meter_display
from ..device.data_collector import DataCollector
from ..storage.data_manager import DataManager
from ..storage.data_models import PowerMeasurement
from ..utils.logger import get_logger
from ..utils.performance import PerformanceMonitor


class DP100Dashboard:
    """Main dashboard application for DP100 Monitor."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize dashboard.
        
        Args:
            config: Application configuration
        """
        self.config = config
        self.logger = get_logger('gui.dashboard')
        
        # Components
        self.data_collector = DataCollector(config)
        self.data_manager = DataManager(config)
        self.realtime_plot = RealtimePlot(config)
        self.control_panel = ControlPanel(config)
        self.performance_monitor = PerformanceMonitor(config)
        
        # Application state
        self.collecting = False  # This flag now means "saving to file"
        self.session_active = False
        self.alert: Optional[dbc.Alert] = None

        # Energy meter state
        self.total_mwh = 0.0
        self.total_mah = 0.0
        self.last_integration_timestamp: Optional[datetime] = None
        
        # Background thread management
        self.running = True
        self.device_monitor_thread: Optional[threading.Thread] = None
        
        # Create Dash app
        self.app = dash.Dash(
            __name__,
            external_stylesheets=[dbc.themes.BOOTSTRAP],
            title="DP100 Monitor"
        )
        
        # Setup callbacks
        self._setup_callbacks()
        
        # Start background tasks
        self.performance_monitor.start()
        self.device_monitor_thread = threading.Thread(target=self._device_monitor_loop, daemon=True)
        self.device_monitor_thread.start()
        
        self.logger.info("Dashboard initialized")

    def _device_monitor_loop(self) -> None:
        """Monitors device connection and keeps data collector running."""
        self.logger.info("Device monitor thread started")
        while self.running:
            if not self.data_collector.is_running():
                self.logger.debug("Data collector is not running, attempting to start...")
                try:
                    # This will attempt to connect and start the thread
                    self.data_collector.start()
                except Exception as e:
                    self.logger.error(f"Error starting data collector: {e}")
            
            time.sleep(5)  # Check every 5 seconds
        self.logger.info("Device monitor thread stopped")
    
    def _setup_callbacks(self) -> None:
        """Setup Dash callbacks."""
        
        @self.app.callback(
            [Output('start-button', 'disabled'),
             Output('stop-button', 'disabled'),
             Output('voltage-input', 'disabled'),
             Output('current-input', 'disabled'),
             Output('set-voltage-button', 'disabled'),
             Output('set-current-button', 'disabled'),
             Output('output-switch', 'disabled'),
             Output('connection-status', 'children'),
             Output('alerts-container', 'children')],
            [Input('start-button', 'n_clicks'),
             Input('stop-button', 'n_clicks'),
             Input('set-voltage-button', 'n_clicks'),
             Input('set-current-button', 'n_clicks'),
             Input('output-switch', 'value')],
            [State('session-id-input', 'value'),
             State('voltage-input', 'value'),
             State('current-input', 'value')]
        )
        def handle_controls(start_clicks, stop_clicks, voltage_clicks, current_clicks, output_enabled,
                          session_id, voltage_value, current_value):
            """Handle control button clicks."""
            ctx = callback_context
            if not ctx.triggered:
                return self._get_control_states()
            
            triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
            
            new_alert = None # Will hold the single alert to be displayed
            
            if triggered_id == 'start-button' and start_clicks:
                success = self._start_collection(session_id)
                if success:
                    new_alert = create_alert("Data saving to file started", "success")
                else:
                    new_alert = create_alert("Failed to start data collection", "danger")
            
            elif triggered_id == 'stop-button' and stop_clicks:
                self._stop_collection()
                new_alert = create_alert("Data saving to file stopped", "info")
            
            elif triggered_id == 'set-voltage-button' and voltage_clicks and voltage_value is not None:
                success = self._set_voltage(float(voltage_value))
                if success:
                    new_alert = create_alert(f"Voltage set to {voltage_value}V", "success")
                else:
                    new_alert = create_alert("Failed to set voltage", "danger")
            
            elif triggered_id == 'set-current-button' and current_clicks and current_value is not None:
                success = self._set_current(float(current_value))
                if success:
                    new_alert = create_alert(f"Current limit set to {current_value}A", "success")
                else:
                    new_alert = create_alert("Failed to set current", "danger")
            
            elif triggered_id == 'output-switch':
                success = self._set_output(output_enabled)
                state = "enabled" if output_enabled else "disabled"
                if success:
                    new_alert = create_alert(f"Output {state}", "success")
                else:
                    new_alert = create_alert(f"Failed to {state.split()[0]} output", "danger")
            
            self.alert = new_alert
            
            return self._get_control_states()
        
        @self.app.callback(
            [Output('realtime-plot', 'extendData'),
             Output('current-voltage', 'children'),
             Output('current-current', 'children'),
             Output('current-power', 'children'),
             Output('collection-status', 'children'),
             Output('statistics-content', 'children'),
             Output('total-mwh', 'children'),
             Output('total-mah', 'children')],
            [Input('update-interval', 'n_intervals'),
             Input('reset-meter-button', 'n_clicks')]
        )
        def update_display(n_intervals, reset_clicks):
            """Update real-time display components and energy meter."""
            ctx = callback_context
            triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

            # Handle reset button click
            if triggered_id == 'reset-meter-button':
                self.total_mwh = 0.0
                self.total_mah = 0.0
                self.last_integration_timestamp = None
                self.logger.info("Energy meter reset.")

            # 1. Get new data from the collector
            samples = self.data_collector.get_samples(max_count=100)
            
            # 2. Process new data for plotting and saving
            sample_dicts = [s.to_dict() for s in samples]
            extend_data_tuple = self.realtime_plot.add_data_batch(sample_dicts)

            # --- Integration for mWh and mAh ---
            if self.last_integration_timestamp is None and samples:
                self.last_integration_timestamp = samples[0].timestamp
            
            for sample in samples:
                delta_t = (sample.timestamp - self.last_integration_timestamp).total_seconds()
                if delta_t > 0:
                    # mWh = (W * 1000) * (s / 3600)
                    self.total_mwh += (sample.power * 1000) * (delta_t / 3600.0)
                    # mAh = (A * 1000) * (s / 3600)
                    self.total_mah += (sample.current * 1000) * (delta_t / 3600.0)
                self.last_integration_timestamp = sample.timestamp
            
            # Save to file if collecting
            if self.collecting:
                for sample in samples:
                    self.data_manager.add_measurement(sample)

            # If no new points were added after decimation, only update text values
            if extend_data_tuple is None and triggered_id != 'reset-meter-button':
                raise PreventUpdate

            # 3. Get latest values for display
            latest = self.realtime_plot.get_latest_values()
            voltage_text = f"{latest['voltage']:.2f}" if latest['voltage'] is not None else "0.00"
            current_text = f"{latest['current']:.3f}" if latest['current'] is not None else "0.000"
            power_text = f"{latest['power']:.2f}" if latest['power'] is not None else "0.00"

            # 4. Get stats for display
            stats = self.data_collector.get_statistics()
            collection_status_str = "Saving to file" if self.collecting else "Not saving"
            
            status_text = [
                html.P(f"Status: {collection_status_str}", className="mb-1"),
                html.P(f"Rate: {stats.get('samples_per_second', 0):.1f} Hz", className="mb-1")
            ]

            if self.data_collector.is_running():
                statistics_content = format_statistics(stats)
            else:
                statistics_content = html.P("Device not connected.", className="text-muted")

            # 5. Format energy meter values
            mwh_text = f"{self.total_mwh:.2f}"
            mah_text = f"{self.total_mah:.2f}"

            # 6. Return all updates
            return (extend_data_tuple, voltage_text, current_text, power_text, 
                   status_text, statistics_content, mwh_text, mah_text)
        
        @self.app.callback(
            Output('update-interval', 'interval'),
            [Input('update-rate-select', 'value')]
        )
        def update_refresh_rate(rate_ms):
            """Update display refresh rate."""
            return rate_ms or 100
        
        @self.app.callback(
            Output('realtime-plot', 'id'),  # Dummy output
            [Input('time-window-select', 'value')]
        )
        def update_time_window(window_seconds):
            """Update plot time window."""
            if window_seconds:
                self.realtime_plot.set_time_window(int(window_seconds))
            return 'realtime-plot'  # Return same ID
    
    def _get_control_states(self) -> tuple:
        """Get current control states."""
        connected = self.data_collector.is_running()
        
        if connected:
            status_badge = dbc.Badge("Connected", color="success", className="me-2")
        else:
            status_badge = dbc.Badge("Disconnected", color="danger", className="me-2")
        
        connection_status = [status_badge, html.Span("DP100 Status")]
        
        # Control states
        start_disabled = self.collecting
        stop_disabled = not self.collecting
        controls_disabled = not connected
        
        return (
            start_disabled,
            stop_disabled,
            controls_disabled,
            controls_disabled,
            controls_disabled,
            controls_disabled,
            controls_disabled,
            connection_status,
            self.alert
        )
    
    def _start_collection(self, session_id: Optional[str]) -> bool:
        """
        Start saving data to a file.
        
        Args:
            session_id: Optional session identifier
            
        Returns:
            True if started successfully
        """
        try:
            # Start data manager session
            self.data_manager.start_session(session_id)
            
            self.collecting = True
            self.session_active = True
            
            self.logger.info("Data saving to file started")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start saving session: {e}")
            return False
    
    def _stop_collection(self) -> None:
        """Stop saving data to a file."""
        try:
            self.collecting = False
            
            # End data manager session
            if self.session_active:
                self.data_manager.end_session()
                self.session_active = False
            
            self.logger.info("Data saving to file stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping saving session: {e}")
    
    def _set_voltage(self, voltage: float) -> bool:
        """Set DP100 voltage."""
        try:
            return self.data_collector.dp100.set_voltage(voltage)
        except Exception as e:
            self.logger.error(f"Error setting voltage: {e}")
            return False
    
    def _set_current(self, current: float) -> bool:
        """Set DP100 current limit."""
        try:
            return self.data_collector.dp100.set_current(current)
        except Exception as e:
            self.logger.error(f"Error setting current: {e}")
            return False
    
    def _set_output(self, enabled: bool) -> bool:
        """Set DP100 output state."""
        try:
            return self.data_collector.dp100.set_output(enabled)
        except Exception as e:
            self.logger.error(f"Error setting output: {e}")
            return False
    
    def create_layout(self) -> html.Div:
        """
        Create dashboard layout.
        
        Returns:
            Dash HTML layout
        """
        return dbc.Container([
            # Header
            html.H1("DP100 Power Monitor", className="text-center mb-4"),
            
            # Alerts
            create_alerts_container(),
            
            # Main content
            dbc.Row([
                # Left column - Controls
                dbc.Col([
                    self.control_panel.create_layout(),
                    create_energy_meter_display(),
                    create_statistics_display()
                ], width=4),
                
                # Right column - Plot and values
                dbc.Col([
                    self.control_panel.create_current_values_display(),
                    dbc.Card([
                        dbc.CardHeader("Real-time Plot"),
                        dbc.CardBody([
                            dcc.Graph(
                                id='realtime-plot',
                                figure=self.realtime_plot.create_figure(),
                                config={'displayModeBar': True}
                            )
                        ])
                    ])
                ], width=8)
            ]),
            
            # Update interval component
            dcc.Interval(
                id='update-interval',
                interval=100,  # 100ms default
                n_intervals=0
            )
        ], fluid=True)
    
    def run_server(self, host: str = "127.0.0.1", port: int = 8050, debug: bool = False) -> None:
        """
        Run the dashboard server.
        
        Args:
            host: Host address
            port: Port number
            debug: Debug mode
        """
        self.app.layout = self.create_layout()
        
        try:
            self.logger.info(f"Starting dashboard server on {host}:{port}")
            self.app.run(host=host, port=port, debug=debug)
        except KeyboardInterrupt:
            self.logger.info("Dashboard server stopped by user")
        except Exception as e:
            self.logger.error(f"Dashboard server error: {e}")
        finally:
            self._cleanup()
    
    def _cleanup(self) -> None:
        """Cleanup resources."""
        try:
            self.running = False  # Stop background threads

            if self.collecting:
                self._stop_collection()

            if self.data_collector.is_running():
                self.data_collector.stop()

            if self.device_monitor_thread:
                self.device_monitor_thread.join(timeout=2.0)
            
            self.performance_monitor.stop()
            
            self.logger.info("Dashboard cleanup completed")
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")


def create_app(config: Dict[str, Any]) -> DP100Dashboard:
    """
    Create DP100 dashboard application.
    
    Args:
        config: Application configuration
        
    Returns:
        Dashboard application instance
    """
    return DP100Dashboard(config)