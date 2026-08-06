import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    pass


class Config:
    """Configuration loader with deep merging and defaults."""

    DEFAULTS: Dict[str, Any] = {
        "emulator": {
            "executable": "mgba-qt",
            "rom_path": "",
            "lua_script": "scripts/mgba_bridge.lua",
            "window_title_pattern": "mGBA",
            "capture_region": {"x": 0, "y": 0, "width": 480, "height": 320},
            "headless": False,
            "no_sound": True,
            "scale": 3,
        },
        "bridge": {
            "host": "127.0.0.1",
            "port": 9999,
            "connect_timeout": 10.0,
            "read_timeout": 0.05,
            "reconnect_delay": 2.0,
            "max_reconnect_attempts": 10,
        },
        "model": {
            "provider": "ollama",
            "base_url": "http://localhost:11434",
            "model": "llava",
            "vision_model": "llava",
            "text_model": "llama3",
            "context_window": 8192,
            "temperature": 0.7,
            "request_timeout": 60.0,
            "max_retries": 2,
            "retry_delay": 2.0,
        },
        "loop": {
            "decision_interval": 1.5,
            "frame_skip": 2,
            "action_duration_ms": 100,
            "stuck_threshold": 6,
            "stuck_state_window": 30.0,
            "max_consecutive_same": 4,
        },
        "prompt": {
            "system_prompt": (
                "You are an expert Pokémon game-playing AI agent. "
                "Your objective is to progress through the game, "
                "defeat Gym Leaders, collect badges, and ultimately complete the main story. "
                "Always explain your reasoning briefly before choosing an action."
            ),
        },
    }

    def __init__(self, config_path: Optional[str] = None):
        self._data: Dict[str, Any] = self._deep_copy(self.DEFAULTS)
        if config_path:
            self._load(config_path)
        self._validate()

    def _deep_copy(self, obj):
        import copy
        return copy.deepcopy(obj)

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = self._deep_copy(value)
        return base

    def _load(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            raise ConfigError(f"Config file not found: {path}")
        try:
            with open(p, "r") as f:
                user_config = yaml.safe_load(f) or {}
            if not isinstance(user_config, dict):
                raise ConfigError("Config file must contain a YAML mapping")
            self._data = self._deep_merge(self._data, user_config)
            logger.info("Loaded configuration from %s", path)
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in config: {e}") from e

    def _validate(self) -> None:
        required = [
            ("emulator", "executable"),
            ("emulator", "rom_path"),
            ("bridge", "port"),
            ("model", "base_url"),
            ("loop", "decision_interval"),
        ]
        for section, key in required:
            if not self._data.get(section, {}).get(key):
                raise ConfigError(f"Missing required config: {section}.{key}")
        if self._data["loop"]["decision_interval"] <= 0:
            raise ConfigError("loop.decision_interval must be positive")
        if self._data["bridge"]["port"] < 1 or self._data["bridge"]["port"] > 65535:
            raise ConfigError("bridge.port must be a valid TCP port")

    def get(self, key: str, default: Any = None) -> Any:
        parts = key.split(".")
        obj = self._data
        for part in parts:
            if isinstance(obj, dict) and part in obj:
                obj = obj[part]
            else:
                return default
        return obj

    def __getitem__(self, key: str) -> Any:
        result = self.get(key)
        if result is None:
            raise KeyError(key)
        return result

    def as_dict(self) -> Dict[str, Any]:
        return self._deep_copy(self._data)
