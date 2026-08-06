from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict


class KernelSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    environment: str = "development"
    log_level: str = "INFO"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_settings(
    *,
    defaults: dict[str, Any] | None = None,
    config_path: Path | None = None,
    env_prefix: str = "KERNEL_",
) -> KernelSettings:
    """Layered config: defaults -> YAML file -> environment variables."""
    layered: dict[str, Any] = dict(defaults or {})

    if config_path is not None and config_path.exists():
        file_config = yaml.safe_load(config_path.read_text()) or {}
        layered = _deep_merge(layered, file_config)

    env_overrides = {
        key[len(env_prefix) :].lower(): value
        for key, value in os.environ.items()
        if key.startswith(env_prefix)
    }
    layered = _deep_merge(layered, env_overrides)

    return KernelSettings(**layered)


__all__ = ["KernelSettings", "load_settings"]
