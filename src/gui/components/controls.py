"""Control components for DP100 Monitor GUI."""

import dash
from dash import html, dcc, Input, Output, State, callback
import dash_bootstrap_components as dbc
from typing import Dict, Any, Optional, Callable

from ...utils.logger import get_logger


class ControlPanel:
    """Control panel component for DP100 Monitor."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize control panel.
        
        Args:
            config: Application configuration
        """
        self.config = config
        self.logger = get_logger('gui.controls')
        
        # Callbacks
        self.start_callback: Optional[Callable[[], bool]] = None
        self.stop_callback: Optional[Callable[[], None]] = None
        self.set_voltage_callback: Optional[Callable[[float], bool]] = None
        self.set_current_callback: Optional[Callable[[float], bool]] = None
        self.set_output_callback: Optional[Callable[[bool], bool]] = None
    
    def create_layout(self) -> html.Div:
        """
        Create control panel layout.
        
        Returns:
            Dash HTML component
        """
        return html.Div([
            # Status Section
            dbc.Card([
                dbc.CardHeader("System Status"),
                dbc.CardBody([
                    html.Div(id="connection-status", children=[
                        dbc.Badge("Disconnected", color="danger", className="me-2"),
                        html.Span("DP100 Status")
                    ]),
                    html.Hr(),
                    html.Div(id="collection-status", children=[
                        html.P("Collection: Stopped", className="mb-1"),
                        html.P("Samples: 0", className="mb-1"),
                        html.P("Rate: 0.0 Hz", className="mb-1")
                    ])
                ])
            ], className="mb-3"),
            
            # Collection Controls
            dbc.Card([
                dbc.CardHeader("Data Collection"),
                dbc.CardBody([
                    dbc.Row([
                        dbc.Col([
                            dbc.Button(
                                "Start Collection",
                                id="start-button",
                                color="success",
                                size="lg",
                                className="me-2"
                            )
                        ], width=6),
                        dbc.Col([
                            dbc.Button(
                                "Stop Collection",
                                id="stop-button",
                                color="danger",
                                size="lg",
                                disabled=True
                            )
                        ], width=6)
                    ]),
                    html.Hr(),
                    html.Div([
                        html.Label("Session ID (optional):"),
                        dbc.Input(
                            id="session-id-input",
                            type="text",
                            placeholder="Auto-generated if empty",
                            className="mb-2"
                        )
                    ])
                ])
            ], className="mb-3"),
            
            # DP100 Controls
            dbc.Card([
                dbc.CardHeader("DP100 Controls"),
                dbc.CardBody([
                    # Voltage Control
                    html.Div([
                        html.Label("Output Voltage (V):"),
                        dbc.InputGroup([
                            dbc.Input(
                                id="voltage-input",
                                type="number",
                                min=0,
                                max=30,
                                step=0.01,
                                value=0.0,
                                disabled=True
                            ),
                            dbc.Button(
                                "Set",
                                id="set-voltage-button",
                                color="primary",
                                disabled=True
                            )
                        ], className="mb-3")
                    ]),
                    
                    # Current Control
                    html.Div([
                        html.Label("Current Limit (A):"),
                        dbc.InputGroup([
                            dbc.Input(
                                id="current-input",
                                type="number",
                                min=0,
                                max=5,
                                step=0.01,
                                value=0.0,
                                disabled=True
                            ),
                            dbc.Button(
                                "Set",
                                id="set-current-button",
                                color="primary",
                                disabled=True
                            )
                        ], className="mb-3")
                    ]),
                    
                    # Output Control
                    html.Div([
                        dbc.Switch(
                            id="output-switch",
                            label="Output Enable",
                            value=False,
                            disabled=True
                        )
                    ])
                ])
            ], className="mb-3"),
            
            # Settings
            dbc.Card([
                dbc.CardHeader("Display Settings"),
                dbc.CardBody([
                    html.Div([
                        html.Label("Time Window (seconds):"),
                        dbc.Select(
                            id="time-window-select",
                            options=[
                                {"label": "30 seconds", "value": 30},
                                {"label": "1 minute", "value": 60},
                                {"label": "2 minutes", "value": 120},
                                {"label": "5 minutes", "value": 300}
                            ],
                            value=60,
                            className="mb-3"
                        )
                    ]),
                    html.Div([
                        html.Label("Update Rate:"),
                        dbc.Select(
                            id="update-rate-select",
                            options=[
                                {"label": "Fast (50ms)", "value": 50},
                                {"label": "Normal (100ms)", "value": 100},
                                {"label": "Slow (200ms)", "value": 200},
                                {"label": "Very Slow (500ms)", "value": 500}
                            ],
                            value=100,
                            className="mb-3"
                        )
                    ])
                ])
            ])
        ])
    
    def create_current_values_display(self) -> html.Div:
        """
        Create current values display.
        
        Returns:
            Dash HTML component
        """
        return dbc.Card([
            dbc.CardHeader("Current Values"),
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.H4("0.00", id="current-voltage", className="text-primary"),
                        html.P("Voltage (V)", className="mb-0")
                    ], width=4),
                    dbc.Col([
                        html.H4("0.00", id="current-current", className="text-danger"),
                        html.P("Current (A)", className="mb-0")
                    ], width=4),
                    dbc.Col([
                        html.H4("0.00", id="current-power", className="text-success"),
                        html.P("Power (W)", className="mb-0")
                    ], width=4)
                ])
            ])
        ], className="mb-3")
    
    def set_start_callback(self, callback: Callable[[Optional[str]], bool]) -> None:
        """
        Set callback for start button.
        
        Args:
            callback: Function to call when start button is pressed
        """
        self.start_callback = callback
    
    def set_stop_callback(self, callback: Callable[[], None]) -> None:
        """
        Set callback for stop button.
        
        Args:
            callback: Function to call when stop button is pressed
        """
        self.stop_callback = callback
    
    def set_voltage_callback(self, callback: Callable[[float], bool]) -> None:
        """
        Set callback for voltage setting.
        
        Args:
            callback: Function to call when voltage is set
        """
        self.set_voltage_callback = callback
    
    def set_current_callback(self, callback: Callable[[float], bool]) -> None:
        """
        Set callback for current setting.
        
        Args:
            callback: Function to call when current is set
        """
        self.set_current_callback = callback
    
    def set_output_callback(self, callback: Callable[[bool], bool]) -> None:
        """
        Set callback for output control.
        
        Args:
            callback: Function to call when output is toggled
        """
        self.set_output_callback = callback


def create_alerts_container() -> html.Div:
    """
    Create alerts container for notifications.
    
    Returns:
        Dash HTML component
    """
    return html.Div(id="alerts-container", children=[], className="mb-3")


def create_alert(message: str, color: str = "info", dismissable: bool = True) -> dbc.Alert:
    """
    Create alert component.
    
    Args:
        message: Alert message
        color: Alert color (primary, secondary, success, danger, warning, info)
        dismissable: Whether alert can be dismissed
        
    Returns:
        Bootstrap alert component
    """
    return dbc.Alert(
        message,
        color=color,
        dismissable=dismissable,
        duration=5000 if dismissable else None
    )


def create_statistics_display() -> html.Div:
    """
    Create statistics display component.
    
    Returns:
        Dash HTML component
    """
    return dbc.Card([
        dbc.CardHeader("Statistics"),
        dbc.CardBody([
            html.Div(id="statistics-content", children=[
                html.P("No data collected yet", className="text-muted")
            ])
        ])
    ], className="mb-3")


def format_statistics(stats: Dict[str, Any]) -> html.Div:
    """
    Format statistics data for display.
    
    Args:
        stats: Statistics dictionary
        
    Returns:
        Formatted HTML component
    """
    if not stats:
        return html.P("No statistics available", className="text-muted")
    
    items = []
    
    if 'samples_collected' in stats:
        items.append(html.P(f"Samples Collected: {stats['samples_collected']:,}"))
    
    if 'samples_per_second' in stats:
        items.append(html.P(f"Sample Rate: {stats['samples_per_second']:.1f} Hz"))
    
    if 'errors' in stats:
        items.append(html.P(f"Errors: {stats['errors']}", 
                           className="text-danger" if stats['errors'] > 0 else ""))
    
    if 'runtime_seconds' in stats:
        runtime = stats['runtime_seconds']
        hours = int(runtime // 3600)
        minutes = int((runtime % 3600) // 60)
        seconds = int(runtime % 60)
        items.append(html.P(f"Runtime: {hours:02d}:{minutes:02d}:{seconds:02d}"))
    
    if 'queue_size' in stats:
        items.append(html.P(f"Queue Size: {stats['queue_size']}"))
    
    return html.Div(items) if items else html.P("No statistics available", className="text-muted")