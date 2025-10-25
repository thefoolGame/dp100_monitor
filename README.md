# DP100 Monitor

Real-time power monitoring for Alientek DP100 power supply with high-frequency data collection and live visualization.

## Features

- **High-frequency data collection**: 10-50 Hz sampling rate
- **Real-time visualization**: Live dashboard with fast refresh rates (100-200ms)
- **Data storage**: HDF5 for performance, CSV for compatibility
- **Session management**: Automatic file rotation and data backup
- **Memory efficient**: Circular buffers and optimized data handling

## Requirements

- Python 3.10+
- Alientek DP100 power supply
- USB-A to USB-A cable
- Linux/Windows/macOS

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

Edit `config/default.yaml` to customize:
- Sampling rate (10-50 Hz)
- GUI refresh rate (100-200ms)
- Storage settings
- Logging options

## Usage

1. Connect DP100 via USB-A cable
2. Set DP100 to USBD mode (double-tap ◀ button)
3. Run the application:
```bash
poetry run python main.py
```

4. Open web browser to `http://localhost:8050`

## Data Files

- **Live sessions**: `data/sessions/YYYY-MM-DD_HH-mm-ss.h5`
- **CSV exports**: `data/exports/session_YYYY-MM-DD_HH-mm-ss.csv`
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

```
src/
├── device/          # DP100 communication
├── gui/             # Dash dashboard
├── storage/         # Data persistence
└── utils/           # Configuration & logging
```

## License

MIT License