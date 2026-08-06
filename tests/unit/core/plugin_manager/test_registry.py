from __future__ import annotations

import pytest

from core.plugin_manager.registry import PluginRegistry, PluginRegistryError


class _Widget:
    def __init__(self, size: int) -> None:
        self.size = size


def test_register_and_create() -> None:
    registry: PluginRegistry[_Widget] = PluginRegistry()
    registry.register("small", lambda: _Widget(size=1))

    widget = registry.create("small")

    assert isinstance(widget, _Widget)
    assert widget.size == 1


def test_create_returns_a_fresh_instance_each_time() -> None:
    registry: PluginRegistry[_Widget] = PluginRegistry()
    registry.register("small", lambda: _Widget(size=1))

    assert registry.create("small") is not registry.create("small")


def test_duplicate_registration_raises() -> None:
    registry: PluginRegistry[_Widget] = PluginRegistry()
    registry.register("small", lambda: _Widget(size=1))

    with pytest.raises(PluginRegistryError):
        registry.register("small", lambda: _Widget(size=2))


def test_create_unregistered_raises() -> None:
    registry: PluginRegistry[_Widget] = PluginRegistry()

    with pytest.raises(PluginRegistryError):
        registry.create("does_not_exist")


def test_names_lists_registered_plugins_sorted() -> None:
    registry: PluginRegistry[_Widget] = PluginRegistry()
    registry.register("zeta", lambda: _Widget(size=1))
    registry.register("alpha", lambda: _Widget(size=2))

    assert registry.names() == ["alpha", "zeta"]
