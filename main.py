#!/usr/bin/env python3
"""
DP100 Monitor - Real-time power monitoring for Alientek DP100

Entry point for the application.
"""

import sys
import logging
from pathlib import Path

from src.utils.config import load_config
from src.utils.logger import setup_logging


def main():
    """Main application entry point."""
    try:
        # Load configuration
        config = load_config()
        
        # Setup logging
        setup_logging(config)
        logger = logging.getLogger("dp100_monitor.main")
        
        logger.info("Starting DP100 Monitor")
        logger.info(f"Configuration loaded: {config['device']['sampling_rate']}Hz sampling")
        
        # Import and start the dashboard
        from src.gui.dashboard import create_app
        
        app = create_app(config)
        
        # Run the dashboard
        app.run_server(
            host=config["gui"]["host"],
            port=config["gui"]["port"],
            debug=config["gui"]["debug"]
        )
        
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())