from __future__ import annotations

from connectors.mt_common.symbols import SymbolMapper
from core.interfaces.types import Symbol


def test_to_broker_appends_suffix() -> None:
    mapper = SymbolMapper(suffix=".m")
    assert mapper.to_broker(Symbol(name="eurusd")) == "EURUSD.m"


def test_from_broker_strips_suffix() -> None:
    mapper = SymbolMapper(suffix=".m")
    symbol = mapper.from_broker("EURUSD.m")
    assert symbol.name == "EURUSD"
    assert symbol.broker_suffix == ".m"


def test_no_suffix_roundtrip() -> None:
    mapper = SymbolMapper()
    assert mapper.to_broker(Symbol(name="GBPUSD")) == "GBPUSD"
    assert mapper.from_broker("GBPUSD").name == "GBPUSD"
