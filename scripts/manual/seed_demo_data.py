"""Seeds a local SQLite database with SYNTHETIC data so
scripts/manual/dashboard/app.py can be previewed on localhost without any
MT5 terminal, broker account, or network access.

Every bar is a randomly generated random walk -- never real market data,
and deliberately not modeling any real market's statistical properties
(no volatility clustering, no session structure). But every signal and
its evidence comes from running the platform's REAL
strategies.composite.signal_fusion_strategy.SignalFusionStrategy (the
same module roster and SignalFusion consensus logic used against a real
account) against those synthetic bars -- not fabricated numbers, but the
real code's genuine output when fed obviously-synthetic input.

The demo symbol is deliberately named "DEMOFX" (not a name any real
broker uses) and the account snapshot is a fixed, clearly-labeled demo
balance -- nothing here should ever be mistaken for a real account or
real market data. This script places no orders and runs no backtest
fills, so the dashboard's trade journal and performance tab show their
existing, honest "not enough data yet" empty state, exactly as they
would for a brand-new real account.

Run (from the repository root, no setup beyond `pip install -e .`):
    python scripts/manual/seed_demo_data.py

Then view it -- either the one-command launcher:
    python scripts/manual/run_demo_dashboard.py
or manually:
    pip install -e ".[dashboard]"
    streamlit run scripts/manual/dashboard/app.py -- \
        --db-path demo.db --symbol DEMOFX --timeframe M15 --demo
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from core.interfaces.types import AccountState, Bar, MarketContext, Symbol, Timeframe
from core.risk.sizing import FixedVolumeSizingModel
from core.signal.engine import SignalEngine
from core.signal.fusion import SignalFusion
from database.repository import SqliteSignalRepository
from decision_engine.engine import DecisionEngine
from strategies.composite.module_roster import build_default_module_roster
from strategies.composite.signal_fusion_strategy import SignalFusionStrategy

DEMO_SYMBOL_NAME = "DEMOFX"
DEMO_TIMEFRAME = Timeframe.M15
DEMO_BAR_COUNT = 400
DEMO_STARTING_PRICE = 1.10000
DEMO_STARTING_BALANCE = 10_000.0
DEMO_DB_PATH = "demo.db"


def _generate_synthetic_bars(*, seed: int, count: int) -> tuple[Bar, ...]:
    rng = random.Random(seed)
    symbol = Symbol(name=DEMO_SYMBOL_NAME)
    price = DEMO_STARTING_PRICE
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=15 * count)

    bars = []
    for i in range(count):
        open_price = price
        close_price = max(0.5, open_price + rng.gauss(0, 0.00025))
        high_price = max(open_price, close_price) + abs(rng.gauss(0, 0.0001))
        low_price = min(open_price, close_price) - abs(rng.gauss(0, 0.0001))
        bars.append(
            Bar(
                symbol=symbol,
                timeframe=DEMO_TIMEFRAME,
                timestamp=start + timedelta(minutes=15 * i),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=abs(rng.gauss(500, 100)),
            )
        )
        price = close_price
    return tuple(bars)


def seed(
    *, db_path: str = DEMO_DB_PATH, seed_value: int = 42, bar_count: int = DEMO_BAR_COUNT
) -> int:
    """Writes synthetic bars, real signals, and a demo account snapshot to
    db_path. Returns the number of signals recorded.
    """
    repository = SqliteSignalRepository(f"sqlite:///{db_path}")
    bars = _generate_synthetic_bars(seed=seed_value, count=bar_count)
    repository.bulk_record_bars(bars)

    engine = SignalEngine(SignalFusion(threshold=0.6))
    for module in build_default_module_roster(higher_timeframe=None):
        engine.register_module(module)
    strategy = SignalFusionStrategy(engine, lookback=300)
    decision_engine = DecisionEngine(FixedVolumeSizingModel(0.01))

    signal_count = 0
    history: list[Bar] = []
    for bar in bars:
        history.append(bar)
        signal = strategy.on_bar(bar)
        if signal is None:
            continue
        context = MarketContext(symbol=bar.symbol, bars=tuple(history[-300:]))
        report = decision_engine.decide(signal, context, equity=DEMO_STARTING_BALANCE)
        repository.record_signal(
            report, strategy_name=strategy.strategy_name, entry_price=bar.close
        )
        signal_count += 1

    repository.record_account_snapshot(
        AccountState(
            balance=DEMO_STARTING_BALANCE,
            equity=DEMO_STARTING_BALANCE,
            margin=0.0,
            free_margin=DEMO_STARTING_BALANCE,
            margin_level=None,
            currency="USD",
        )
    )
    return signal_count


def main() -> None:
    signal_count = seed()
    print(f"Seeded {DEMO_DB_PATH} with {DEMO_BAR_COUNT} synthetic bars.")
    print(f"Recorded {signal_count} real signal(s) from the actual SignalFusionStrategy.")
    print(
        "\nThis is SYNTHETIC data for previewing the dashboard UI only -- "
        "no real market data,\nno real account, and no orders were ever placed."
    )


if __name__ == "__main__":
    main()
