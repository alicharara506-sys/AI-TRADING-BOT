from __future__ import annotations

from core.interfaces.indicator import Indicator
from core.plugin_manager.registry import PluginRegistry, PluginRegistryError

IndicatorRegistryError = PluginRegistryError


class IndicatorRegistry(PluginRegistry[Indicator]):
    """Named indicator factories, so live trading, backtesting, optimization, and
    analytics all construct the exact same indicator implementation by name.
    See core.plugin_manager.registry.PluginRegistry for the general pattern this
    specializes.
    """


__all__ = ["IndicatorRegistry", "IndicatorRegistryError"]
