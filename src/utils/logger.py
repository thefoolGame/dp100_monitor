"""Logging setup for DP100 Monitor."""

import logging
import logging.config
import yaml
from pathlib import Path
from typing import Dict, Any


def setup_logging(config: Dict[str, Any]) -> None:
    """
    Setup logging configuration.

    Args:
        config: Application configuration dictionary
    """
    # Ensure logs directory exists
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Try to load logging configuration from file
    logging_config_path = Path("config/logging.yaml")

    if logging_config_path.exists():
        try:
            with open(logging_config_path, "r", encoding="utf-8") as f:
                logging_config = yaml.safe_load(f)
            logging.config.dictConfig(logging_config)
            return
        except Exception as e:
            print(f"Warning: Could not load logging config from file: {e}")

    # Fallback to basic configuration from main config
    log_level = getattr(logging, config.get("logging", {}).get("level", "INFO").upper())
    log_format = config.get("logging", {}).get(
        "format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Setup basic logging
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "dp100-monitor.log"),
        ],
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    return logging.getLogger(f"dp100_monitor.{name}")
