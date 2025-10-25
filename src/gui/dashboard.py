"""Main dashboard for DP100 Monitor."""

import dash
from dash import html, dcc, Input, Output, State, callback_context
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional

from .components.realtime_plot import RealtimePlot
from .components.controls import ControlPanel, create_alerts_container, create_alert, create_statistics_display, format_statistics
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
        self.collecting = False
        self.session_active = False
        self.alerts = []
        
        # Data update thread
        self.update_thread: Optional[threading.Thread] = None
        self.running = False
        
        # Create Dash app
        self.app = dash.Dash(
            __name__,
            external_stylesheets=[dbc.themes.BOOTSTRAP],
            title="DP100 Monitor"
        )
        
        # Setup callbacks
        self._setup_callbacks()
        
        # Start performance monitoring
        self.performance_monitor.start()
        
        # Try to connect to DP100 automatically
        self._try_connect_dp100()
        
        self.logger.info("Dashboard initialized")
    
    def _try_connect_dp100(self) -> None:
        """Try to connect to DP100 device automatically."""
        try:
            # Attempt to connect without starting full data collection
            if self.data_collector.dp100.connect():
                self.logger.info("DP100 connected automatically")
            else:
                self.logger.info("DP100 not available for automatic connection")
        except Exception as e:
            self.logger.debug(f"Auto-connection attempt failed: {e}")
    
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
            
            alerts = list(self.alerts)  # Copy current alerts
            
            if triggered_id == 'start-button' and start_clicks:
                success = self._start_collection(session_id)
                if success:
                    alerts.append(create_alert("Data collection started", "success"))
                else:
                    alerts.append(create_alert("Failed to start data collection", "danger"))
            
            elif triggered_id == 'stop-button' and stop_clicks:
                self._stop_collection()
                alerts.append(create_alert("Data collection stopped", "info"))
            
            elif triggered_id == 'set-voltage-button' and voltage_clicks and voltage_value is not None:
                success = self._set_voltage(voltage_value)
                if success:
                    alerts.append(create_alert(f"Voltage set to {voltage_value}V", "success"))
                else:
                    alerts.append(create_alert("Failed to set voltage", "danger"))
            
            elif triggered_id == 'set-current-button' and current_clicks and current_value is not None:
                success = self._set_current(current_value)
                if success:
                    alerts.append(create_alert(f"Current limit set to {current_value}A", "success"))
                else:
                    alerts.append(create_alert("Failed to set current", "danger"))
            
            elif triggered_id == 'output-switch':
                success = self._set_output(output_enabled)
                state = "enabled" if output_enabled else "disabled"
                if success:
                    alerts.append(create_alert(f"Output {state}", "success"))
                else:
                    alerts.append(create_alert(f"Failed to {state.split()[0]} output", "danger"))
            
            # Limit alerts to last 5
            self.alerts = alerts[-5:]
            
            return self._get_control_states()
        
        @self.app.callback(
            [Output('realtime-plot', 'figure'),
             Output('current-voltage', 'children'),
             Output('current-current', 'children'),
             Output('current-power', 'children'),
             Output('collection-status', 'children'),
             Output('statistics-content', 'children')],
            [Input('update-interval', 'n_intervals')]
        )
        def update_display(n_intervals):
            """Update real-time display."""
            # Get new data from collector
            if self.collecting:
                samples = self.data_collector.get_samples(max_count=50)
                for sample in samples:
                    self.realtime_plot.add_data_point(
                        sample.timestamp,
                        sample.voltage,
                        sample.current,
                        sample.power
                    )
                    
                    # Add to data manager
                    self.data_manager.add_measurement(sample)
            
            # Create plot
            figure = self.realtime_plot.create_figure()
            
            # Get latest values
            latest = self.realtime_plot.get_latest_values()
            
            # Format current values
            voltage_text = f"{latest['voltage']:.2f}" if latest['voltage'] is not None else "0.00"
            current_text = f"{latest['current']:.3f}" if latest['current'] is not None else "0.000"
            power_text = f"{latest['power']:.2f}" if latest['power'] is not None else "0.00"
            
            # Collection status
            if self.collecting:
                stats = self.data_collector.get_statistics()
                status_text = [
                    html.P(f"Collection: Running", className="mb-1"),
                    html.P(f"Samples: {stats.get('samples_collected', 0):,}", className="mb-1"),
                    html.P(f"Rate: {stats.get('samples_per_second', 0):.1f} Hz", className="mb-1")
                ]
                statistics_content = format_statistics(stats)
            else:
                status_text = [
                    html.P("Collection: Stopped", className="mb-1"),
                    html.P("Samples: 0", className="mb-1"),
                    html.P("Rate: 0.0 Hz", className="mb-1")
                ]
                statistics_content = html.P("No data collected yet", className="text-muted")
            
            return (figure, voltage_text, current_text, power_text, 
                   status_text, statistics_content)
        
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
                self.realtime_plot.set_time_window(window_seconds)
            return 'realtime-plot'  # Return same ID
    
    def _get_control_states(self) -> tuple:
        """Get current control states."""
        # Connection status
        connected = self.data_collector.dp100.is_connected() if hasattr(self.data_collector, 'dp100') else False
        
        if connected:
            status_badge = dbc.Badge("Connected", color="success", className="me-2")
        else:
            status_badge = dbc.Badge("Disconnected", color="danger", className="me-2")
        
        connection_status = [status_badge, html.Span("DP100 Status")]
        
        # Control states
        start_disabled = self.collecting
        stop_disabled = not self.collecting
        controls_disabled = not connected or self.collecting
        
        return (
            start_disabled,           # start-button disabled
            stop_disabled,            # stop-button disabled
            controls_disabled,        # voltage-input disabled
            controls_disabled,        # current-input disabled
            controls_disabled,        # set-voltage-button disabled
            controls_disabled,        # set-current-button disabled
            controls_disabled,        # output-switch disabled
            connection_status,        # connection-status children
            self.alerts              # alerts-container children
        )
    
    def _start_collection(self, session_id: Optional[str]) -> bool:
        """
        Start data collection.
        
        Args:
            session_id: Optional session identifier
            
        Returns:
            True if started successfully
        """
        try:
            # Start data collector
            if not self.data_collector.start():
                return False
            
            # Start data manager session
            self.data_manager.start_session(session_id)
            
            self.collecting = True
            self.session_active = True
            
            self.logger.info("Data collection started")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start collection: {e}")
            return False
    
    def _stop_collection(self) -> None:
        """Stop data collection."""
        try:
            self.collecting = False
            
            # Stop data collector
            self.data_collector.stop()
            
            # End data manager session
            if self.session_active:
                self.data_manager.end_session()
                self.session_active = False
            
            self.logger.info("Data collection stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping collection: {e}")
    
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
            if self.collecting:
                self._stop_collection()
            
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