"""Configuration management for DP100 Monitor."""

import yaml
from pathlib import Path
from typing import Dict, Any


def load_config(config_path: str = "config/default.yaml") -> Dict[str, Any]:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If configuration file not found
        yaml.YAMLError: If configuration file is invalid
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # Validate required sections
        required_sections = ['device', 'gui', 'storage', 'logging']
        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required configuration section: {section}")
        
        return config
        
    except yaml.YAMLError as e:
        raise yaml.YAMLError(f"Invalid YAML in configuration file: {e}")


def validate_config(config: Dict[str, Any]) -> bool:
    """
    Validate configuration parameters.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        True if valid
        
    Raises:
        ValueError: If configuration is invalid
    """
    # Validate sampling rate
    sampling_rate = config['device']['sampling_rate']
    if not 1 <= sampling_rate <= 100:
        raise ValueError(f"Invalid sampling rate: {sampling_rate} (must be 1-100 Hz)")
    
    # Validate GUI refresh rate
    refresh_rate = config['gui']['refresh_rate']
    if not 50 <= refresh_rate <= 1000:
        raise ValueError(f"Invalid refresh rate: {refresh_rate} (must be 50-1000 ms)")
    
    # Validate buffer size
    buffer_size = config['storage']['buffer_size']
    if buffer_size < 100:
        raise ValueError(f"Buffer size too small: {buffer_size} (minimum 100)")
    
    return True