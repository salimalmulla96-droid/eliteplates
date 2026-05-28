"""
Alert Configuration Module

Manages cooldown periods, timing, and other alert settings.
Supports both environment variables and config file overrides.
"""

import os
import json
from pathlib import Path
from typing import Any
import logging

logger = logging.getLogger(__name__)


class AlertConfig:
    """Configuration for alert behavior."""
    
    # Cooldown presets (in seconds)
    COOLDOWN_PRESETS = {
        '20s': 20,
        '30s': 30,
        '1m': 60,
        '5m': 300,
        '7m': 420,  # Default
        '10m': 600,
        '30m': 1800,
        '1h': 3600,
        '2h': 7200,
        '6h': 21600,
        '1d': 86400,
    }
    
    def __init__(self):
        """Initialize configuration from environment and config file."""
        self.duplicate_cooldown_seconds = self._get_cooldown()
        self.enable_plate_tracking = self._get_bool('ENABLE_PLATE_TRACKING', True)
        self.enable_dedup_messages = self._get_bool('ENABLE_DEDUP_MESSAGES', True)
        self.cleanup_old_plates_days = self._get_int('CLEANUP_OLD_PLATES_DAYS', 30)
        self.max_retries = self._get_int('MAX_ALERT_RETRIES', 3)
        self.retry_delay_seconds = self._get_int('RETRY_DELAY_SECONDS', 5)
        self.include_release_count = self._get_bool('INCLUDE_RELEASE_COUNT', True)
        
    def _get_cooldown(self) -> int:
        """Get duplicate cooldown period in seconds."""
        # Try env variable first
        env_val = os.getenv('DUPLICATE_COOLDOWN_SECONDS')
        if env_val:
            try:
                return int(env_val)
            except ValueError:
                logger.warning(f"Invalid DUPLICATE_COOLDOWN_SECONDS: {env_val}")
        
        # Try preset from env
        env_preset = os.getenv('DUPLICATE_COOLDOWN_PRESET', '7m')
        if env_preset in self.COOLDOWN_PRESETS:
            return self.COOLDOWN_PRESETS[env_preset]
        
        # Try config file
        config = self._load_config_file()
        if 'duplicate_cooldown_seconds' in config:
            return int(config['duplicate_cooldown_seconds'])
        if 'duplicate_cooldown_preset' in config:
            preset = config['duplicate_cooldown_preset']
            return self.COOLDOWN_PRESETS.get(preset, 420)
        
        # Default: 7 minutes
        return 420
    
    def _get_bool(self, env_key: str, default: bool = True) -> bool:
        """Get boolean from environment or config."""
        env_val = os.getenv(env_key)
        if env_val:
            return env_val.lower() in {'true', '1', 'yes', 'on'}
        
        config = self._load_config_file()
        key = env_key.lower()
        if key in config:
            val = config[key]
            if isinstance(val, bool):
                return val
            return str(val).lower() in {'true', '1', 'yes', 'on'}
        
        return default
    
    def _get_int(self, env_key: str, default: int = 0) -> int:
        """Get integer from environment or config."""
        env_val = os.getenv(env_key)
        if env_val:
            try:
                return int(env_val)
            except ValueError:
                logger.warning(f"Invalid {env_key}: {env_val}")
        
        config = self._load_config_file()
        key = env_key.lower()
        if key in config:
            try:
                return int(config[key])
            except (ValueError, TypeError):
                logger.warning(f"Invalid {key} in config: {config[key]}")
        
        return default
    
    def _load_config_file(self) -> dict[str, Any]:
        """Load configuration from JSON file if it exists."""
        config_path = Path(__file__).parent.parent.parent / 'alert_config.json'
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load config file: {e}")
        return {}
    
    def to_dict(self) -> dict[str, Any]:
        """Export config as dictionary."""
        return {
            'duplicate_cooldown_seconds': self.duplicate_cooldown_seconds,
            'enable_plate_tracking': self.enable_plate_tracking,
            'enable_dedup_messages': self.enable_dedup_messages,
            'cleanup_old_plates_days': self.cleanup_old_plates_days,
            'max_retries': self.max_retries,
            'retry_delay_seconds': self.retry_delay_seconds,
            'include_release_count': self.include_release_count,
        }


# Global config instance
config = AlertConfig()


def get_config() -> AlertConfig:
    """Get the global alert configuration."""
    return config


def reload_config() -> None:
    """Reload configuration from environment and file."""
    global config
    config = AlertConfig()
    logger.info(f"Alert config reloaded: {config.to_dict()}")
