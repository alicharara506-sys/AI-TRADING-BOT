from __future__ import annotations

from pathlib import Path

import pytest

from core.config.settings import load_settings


def test_defaults_only() -> None:
    settings = load_settings(defaults={"environment": "test", "log_level": "DEBUG"})

    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"


def test_file_overrides_defaults(tmp_path: Path) -> None:
    config_file = tmp_path / "settings.yaml"
    config_file.write_text("log_level: WARNING\n")

    settings = load_settings(
        defaults={"environment": "test", "log_level": "DEBUG"},
        config_path=config_file,
    )

    assert settings.log_level == "WARNING"
    assert settings.environment == "test"


def test_env_overrides_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_file = tmp_path / "settings.yaml"
    config_file.write_text("log_level: WARNING\n")
    monkeypatch.setenv("KERNEL_LOG_LEVEL", "ERROR")

    settings = load_settings(
        defaults={"environment": "test", "log_level": "DEBUG"},
        config_path=config_file,
    )

    assert settings.log_level == "ERROR"


def test_missing_config_file_falls_back_to_defaults(tmp_path: Path) -> None:
    settings = load_settings(
        defaults={"environment": "test"},
        config_path=tmp_path / "does-not-exist.yaml",
    )

    assert settings.environment == "test"
