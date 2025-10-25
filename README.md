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
git clone https://github.com/thefoolGame/dp100_monitor.git
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

The application's behavior can be customized by editing the `config/default.yaml` file.

### `device`
- `sampling_rate`: The target number of measurements to take per second (Hz).
- `usb_timeout`: Timeout in milliseconds for USB communication.
- `reconnect_attempts`: Number of times to try reconnecting if the connection is lost.
- `reconnect_delay`: Seconds to wait between reconnection attempts.

### `gui`
- `refresh_rate`: How often the web dashboard updates, in milliseconds (e.g., 100ms = 10 Hz).
- `plot_window`: The time window displayed on the real-time plot, in seconds.
- `decimation_factor`: To improve rendering performance, the plot only displays 1 out of every N samples. This sets N (e.g., 5 means 1/5th of points are shown).
- `host`, `port`, `debug`: Standard network settings for the web server.

### `storage`
- `buffer_size`: Number of samples to buffer in memory before writing a batch to the HDF5 file.
- `compression`: The compression algorithm to use for HDF5 files (e.g., `gzip`). Set to `null` to disable.
- `compression_level`: Compression level from 1 (fastest) to 9 (best compression).

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