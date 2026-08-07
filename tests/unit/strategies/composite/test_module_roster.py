from __future__ import annotations

from core.interfaces.analysis import AnalysisModule
from core.interfaces.types import Timeframe
from strategies.composite.module_roster import build_default_module_roster


def test_returns_analysis_modules_with_unique_names() -> None:
    roster = build_default_module_roster()

    assert len(roster) > 10
    for module in roster:
        assert isinstance(module, AnalysisModule)

    names = [module.name for module in roster]
    assert len(names) == len(set(names))


def test_includes_higher_timeframe_alignment_by_default() -> None:
    roster = build_default_module_roster()

    assert any(module.name == "higher_timeframe_alignment" for module in roster)


def test_omits_higher_timeframe_alignment_when_disabled() -> None:
    roster = build_default_module_roster(higher_timeframe=None)

    assert not any(module.name == "higher_timeframe_alignment" for module in roster)
    assert len(roster) == len(build_default_module_roster()) - 1


def test_higher_timeframe_is_configurable() -> None:
    roster = build_default_module_roster(higher_timeframe=Timeframe.D1)
    alignment_modules = [m for m in roster if m.name == "higher_timeframe_alignment"]

    assert len(alignment_modules) == 1
