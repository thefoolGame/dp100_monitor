# DP100 Monitor

Real-time power monitoring for Alientek DP100 power supply with high-frequency data collection, live visualization, and device control.

## Features

- **High-frequency data collection**: Target sampling rate of 50 Hz.
- **Real-time visualization**: Live dashboard with efficient plot updates.
- **Device Control**: Remote control of voltage, current, and output state via the web UI.
- **Energy Metering**: Cumulative calculation of mWh and mAh consumption with a manual reset.
- **Data storage**: Robust HDF5 for live recording, with automatic export to CSV for compatibility.
- **Session management**: Data is organized into sessions, named by timestamp or a custom ID.

## Requirements

- Python 3.10+
- Poetry for dependency management
- Alientek DP100 power supply

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd dp100
```

2. Install dependencies using Poetry:
```bash
poetry install
```

3. Activate the virtual environment:
```bash
poetry shell
```

## Configuration

Edit `config/default.yaml` to customize application behavior. Most settings are functional, but some are not fully implemented.

- **`device`**: All settings (sampling_rate, usb_timeout, etc.) are functional.
- **`gui`**: All settings (refresh_rate, plot_window, etc.) are functional.
- **`storage`**: 
    - `buffer_size` and `compression` settings are used.
    - `backup_interval` is obsolete after recent refactoring.
    - `session_duration` and `max_memory_mb` are currently not implemented.

## Usage

1. Connect DP100 via USB-A cable.
2. Set DP100 to **USBD mode** (double-tap the ◀ button on the device).
3. Run the application:
```bash
poetry run python main.py
```

4. Open a web browser to `http://localhost:8050`

## Data Files

- **HDF5 Master Files**: `data/sessions/YYYY-MM-DD_HH-mm-ss.h5`
- **CSV Exports**: `data/exports/session_YYYY-MM-DD_HH-mm-ss.csv`
- **Logs**: `logs/dp100-monitor.log`

## Development

Run tests:
```bash
poetry run pytest
```

Code formatting:
```bash
poetry run black src/ tests/
```

Type checking:
```bash
poetry run mypy src/
```

## Architecture

The application is structured into four main layers:

- **`src/device/`**: Handles low-level device communication.
    - `dp100_interface.py`: Manages the USB HID protocol, including command formatting and parsing data packets.
    - `data_collector.py`: Runs a high-frequency background thread to continuously sample data from the device.

- **`src/gui/`**: Contains the Dash web application.
    - `dashboard.py`: The main class that orchestrates the UI, callbacks, and application state.
    - `components/`: Reusable UI modules like the plot and control panels.

- **`src/storage/`**: Manages data persistence.
    - `data_manager.py`: Handles the creation of HDF5 files and the final export to CSV.

- **`src/utils/`**: Shared utilities for configuration, logging, etc.

## License

MIT License