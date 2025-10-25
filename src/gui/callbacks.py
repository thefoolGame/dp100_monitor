"""Dash callbacks for DP100 Monitor."""

from dash import Input, Output, State, callback_context
from typing import Dict, Any, List, Tuple, Optional

from ..utils.logger import get_logger


class CallbackManager:
    """Manages Dash callbacks for the DP100 Monitor."""
    
    def __init__(self, dashboard):
        """
        Initialize callback manager.
        
        Args:
            dashboard: Dashboard instance
        """
        self.dashboard = dashboard
        self.logger = get_logger('gui.callbacks')
    
    def register_callbacks(self) -> None:
        """Register all dashboard callbacks."""
        self._register_control_callbacks()
        self._register_display_callbacks()
        self._register_settings_callbacks()
    
    def _register_control_callbacks(self) -> None:
        """Register control-related callbacks."""
        
        @self.dashboard.app.callback(
            [Output('start-button', 'disabled'),
             Output('stop-button', 'disabled'),
             Output('session-status', 'children')],
            [Input('start-button', 'n_clicks'),
             Input('stop-button', 'n_clicks')],
            [State('session-id-input', 'value')]
        )
        def handle_collection_controls(start_clicks, stop_clicks, session_id):
            """Handle start/stop collection buttons."""
            ctx = callback_context
            
            if not ctx.triggered:
                return self._get_button_states()
            
            triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
            
            if triggered_id == 'start-button' and start_clicks:
                success = self.dashboard._start_collection(session_id)
                if success:
                    self.logger.info("Collection started from UI")
                else:
                    self.logger.error("Failed to start collection from UI")
            
            elif triggered_id == 'stop-button' and stop_clicks:
                self.dashboard._stop_collection()
                self.logger.info("Collection stopped from UI")
            
            return self._get_button_states()
        
        @self.dashboard.app.callback(
            Output('device-status', 'children'),
            [Input('set-voltage-button', 'n_clicks'),
             Input('set-current-button', 'n_clicks'),
             Input('output-switch', 'value')],
            [State('voltage-input', 'value'),
             State('current-input', 'value')]
        )
        def handle_device_controls(voltage_clicks, current_clicks, output_enabled,
                                 voltage_value, current_value):
            """Handle DP100 device control callbacks."""
            ctx = callback_context
            
            if not ctx.triggered:
                return self._get_device_status()
            
            triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
            
            if triggered_id == 'set-voltage-button' and voltage_clicks:
                if voltage_value is not None:
                    success = self.dashboard._set_voltage(voltage_value)
                    self.logger.info(f"Voltage set to {voltage_value}V: {'success' if success else 'failed'}")
            
            elif triggered_id == 'set-current-button' and current_clicks:
                if current_value is not None:
                    success = self.dashboard._set_current(current_value)
                    self.logger.info(f"Current set to {current_value}A: {'success' if success else 'failed'}")
            
            elif triggered_id == 'output-switch':
                success = self.dashboard._set_output(output_enabled)
                state = "enabled" if output_enabled else "disabled"
                self.logger.info(f"Output {state}: {'success' if success else 'failed'}")
            
            return self._get_device_status()
    
    def _register_display_callbacks(self) -> None:
        """Register display-related callbacks."""
        
        @self.dashboard.app.callback(
            [Output('realtime-plot', 'figure'),
             Output('current-values', 'children'),
             Output('statistics', 'children')],
            [Input('update-interval', 'n_intervals')]
        )
        def update_realtime_display(n_intervals):
            """Update real-time plot and values."""
            try:
                # Update plot data
                if self.dashboard.collecting:
                    samples = self.dashboard.data_collector.get_samples(max_count=100)
                    for sample in samples:
                        self.dashboard.realtime_plot.add_data_point(
                            sample.timestamp,
                            sample.voltage,
                            sample.current,
                            sample.power
                        )
                
                # Generate plot
                figure = self.dashboard.realtime_plot.create_figure()
                
                # Get current values
                current_values = self._format_current_values()
                
                # Get statistics
                statistics = self._format_statistics()
                
                return figure, current_values, statistics
                
            except Exception as e:
                self.logger.error(f"Error updating display: {e}")
                return {}, "Error loading data", "Error loading statistics"
    
    def _register_settings_callbacks(self) -> None:
        """Register settings-related callbacks."""
        
        @self.dashboard.app.callback(
            Output('update-interval', 'interval'),
            [Input('refresh-rate-select', 'value')]
        )
        def update_refresh_rate(rate_ms):
            """Update display refresh rate."""
            if rate_ms:
                self.logger.debug(f"Refresh rate updated to {rate_ms}ms")
                return rate_ms
            return 100  # Default
        
        @self.dashboard.app.callback(
            Output('plot-settings-status', 'children'),
            [Input('time-window-select', 'value'),
             Input('decimation-select', 'value')]
        )
        def update_plot_settings(window_seconds, decimation_factor):
            """Update plot display settings."""
            try:
                if window_seconds:
                    self.dashboard.realtime_plot.set_time_window(window_seconds)
                    self.logger.debug(f"Time window updated to {window_seconds}s")
                
                if decimation_factor:
                    self.dashboard.realtime_plot.set_decimation_factor(decimation_factor)
                    self.logger.debug(f"Decimation factor updated to {decimation_factor}")
                
                return "Settings updated"
                
            except Exception as e:
                self.logger.error(f"Error updating plot settings: {e}")
                return "Error updating settings"
    
    def _get_button_states(self) -> Tuple[bool, bool, str]:
        """Get current button states."""
        start_disabled = self.dashboard.collecting
        stop_disabled = not self.dashboard.collecting
        
        if self.dashboard.collecting:
            status = "Collection Running"
        else:
            status = "Collection Stopped"
        
        return start_disabled, stop_disabled, status
    
    def _get_device_status(self) -> str:
        """Get current device status."""
        try:
            if hasattr(self.dashboard.data_collector, 'dp100'):
                connected = self.dashboard.data_collector.dp100.is_connected()
                return "Connected" if connected else "Disconnected"
            return "Not initialized"
        except Exception:
            return "Error"
    
    def _format_current_values(self) -> Dict[str, str]:
        """Format current measurement values."""
        try:
            latest = self.dashboard.realtime_plot.get_latest_values()
            
            return {
                'voltage': f"{latest['voltage']:.2f}" if latest['voltage'] is not None else "0.00",
                'current': f"{latest['current']:.3f}" if latest['current'] is not None else "0.000",
                'power': f"{latest['power']:.2f}" if latest['power'] is not None else "0.00"
            }
        except Exception as e:
            self.logger.error(f"Error formatting current values: {e}")
            return {'voltage': "Error", 'current': "Error", 'power': "Error"}
    
    def _format_statistics(self) -> Dict[str, Any]:
        """Format statistics for display."""
        try:
            if self.dashboard.collecting:
                collector_stats = self.dashboard.data_collector.get_statistics()
                plot_stats = self.dashboard.realtime_plot.get_statistics()
                
                return {
                    'samples_collected': collector_stats.get('samples_collected', 0),
                    'sample_rate': collector_stats.get('samples_per_second', 0.0),
                    'errors': collector_stats.get('errors', 0),
                    'queue_size': collector_stats.get('queue_size', 0),
                    'plot_points': plot_stats.get('buffer_size', 0),
                    'plot_update_rate': plot_stats.get('update_rate', 0.0)
                }
            else:
                return {}
        except Exception as e:
            self.logger.error(f"Error formatting statistics: {e}")
            return {'error': str(e)}


def register_error_handlers(app) -> None:
    """
    Register global error handlers for the Dash app.
    
    Args:
        app: Dash application instance
    """
    logger = get_logger('gui.errors')
    
    @app.server.errorhandler(404)
    def not_found(error):
        logger.warning(f"404 error: {error}")
        return "Page not found", 404
    
    @app.server.errorhandler(500)
    def internal_error(error):
        logger.error(f"500 error: {error}")
        return "Internal server error", 500