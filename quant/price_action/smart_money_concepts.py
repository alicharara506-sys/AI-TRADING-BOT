"""Smart Money Concepts (SMC): mechanical, checkable definitions of the
price-action patterns that trading-floor "order flow" analysis names --
fair value gaps, equal highs/lows (liquidity pools), order blocks, and
liquidity sweeps (stop hunts). Every definition here is objective and
reproducible from OHLCV data alone, in the same spirit as this project's
Elliott Wave module: no fabricated "smart money intent," just the
checkable geometric pattern that concept is named after.

Breaker/mitigation blocks (an order block that price later violates and
which then flips role, support becoming resistance or vice versa) are
deliberately not implemented yet: that needs tracking whether a specific
order block zone has since been broken, which is a stateful extension of
find_order_blocks below, not a new primitive -- left for a later pass
rather than shipped half-built.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core.interfaces.types import Bar, Direction, Evidence, MarketContext
from quant.price_action.swings import find_all_swing_points
from quant.technical_analysis.volatility import compute_atr

# -- Fair value gaps -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FairValueGap:
    """A three-candle imbalance: candle `index`'s neighbors don't overlap,
    leaving a price range the market never traded through -- the gap.
    """

    direction_up: bool
    index: int
    gap_low: float
    gap_high: float


def find_fair_value_gaps(bars: Sequence[Bar]) -> list[FairValueGap]:
    """A bullish (up) gap: candle `i-1`'s high sits below candle `i+1`'s low
    -- an untraded range candle `i` (the displacement candle) jumped over.
    A bearish (down) gap is the mirror image.
    """
    gaps: list[FairValueGap] = []
    for i in range(1, len(bars) - 1):
        previous, following = bars[i - 1], bars[i + 1]
        if previous.high < following.low:
            gaps.append(
                FairValueGap(
                    direction_up=True, index=i, gap_low=previous.high, gap_high=following.low
                )
            )
        elif previous.low > following.high:
            gaps.append(
                FairValueGap(
                    direction_up=False, index=i, gap_low=following.high, gap_high=previous.low
                )
            )
    return gaps


class FairValueGapModule:
    """Unfilled fair value gaps act as a support/resistance magnet: when the
    current bar's close sits inside a still-open gap, that's evidence of a
    reaction in the gap's own direction (an up-gap below current price is
    support; a down-gap above is resistance) -- the standard SMC read.
    Confidence peaks at the gap's midpoint and falls off toward either edge,
    the same proximity-scoring shape Fibonacci confluence already uses.
    """

    name = "fair_value_gap"

    def __init__(self, *, lookback: int = 50) -> None:
        if lookback < 3:
            raise ValueError("lookback must be >= 3")
        self._lookback = lookback

    def analyze(self, context: MarketContext) -> list[Evidence]:
        bars = context.bars
        if len(bars) < 4:
            return []

        history = bars[:-1][-self._lookback :]
        gaps = find_fair_value_gaps(history)
        if not gaps:
            return []

        current = bars[-1].close
        for gap in reversed(gaps):
            if not gap.gap_low <= current <= gap.gap_high:
                continue
            half_width = (gap.gap_high - gap.gap_low) / 2
            if half_width <= 0:
                continue
            midpoint = (gap.gap_low + gap.gap_high) / 2
            confidence = max(0.0, 1.0 - abs(current - midpoint) / half_width)
            if confidence <= 0.0:
                continue
            direction = Direction.LONG if gap.direction_up else Direction.SHORT
            return [
                Evidence(
                    source_module=self.name,
                    direction=direction,
                    confidence=confidence,
                    rationale={
                        "gap_low": gap.gap_low,
                        "gap_high": gap.gap_high,
                        "direction_up": gap.direction_up,
                    },
                )
            ]
        return []


# -- Equal highs / equal lows (liquidity pools) ---------------------------------


@dataclass(frozen=True, slots=True)
class EqualLevel:
    """Two consecutive confirmed swing highs (or lows) sitting within
    `tolerance` of each other -- the resting liquidity pool a stop-hunt
    (find_liquidity_sweeps below) typically targets.
    """

    is_high: bool
    index_a: int
    index_b: int
    price: float


def find_equal_highs_lows(
    bars: Sequence[Bar], *, swing_arm: int = 2, tolerance: float = 0.0005
) -> list[EqualLevel]:
    """`tolerance` is a fraction of price (e.g. 0.0005 = 0.05%), applied to
    each *consecutive* pair of confirmed swing highs (and separately, swing
    lows) -- not every pair, since a resting liquidity pool is a level
    price revisited without an intervening opposite swing invalidating it.
    """
    if swing_arm < 1:
        raise ValueError("swing_arm must be >= 1")
    if tolerance <= 0:
        raise ValueError("tolerance must be > 0")

    points = find_all_swing_points(bars, arm=swing_arm)
    highs = [(index, bars[index].high) for index, kind in points if kind == "high"]
    lows = [(index, bars[index].low) for index, kind in points if kind == "low"]

    levels: list[EqualLevel] = []
    for (index_a, price_a), (index_b, price_b) in zip(highs, highs[1:], strict=False):
        if abs(price_a - price_b) <= tolerance * max(price_a, price_b):
            levels.append(
                EqualLevel(
                    is_high=True, index_a=index_a, index_b=index_b, price=(price_a + price_b) / 2
                )
            )
    for (index_a, price_a), (index_b, price_b) in zip(lows, lows[1:], strict=False):
        if abs(price_a - price_b) <= tolerance * max(price_a, price_b):
            levels.append(
                EqualLevel(
                    is_high=False, index_a=index_a, index_b=index_b, price=(price_a + price_b) / 2
                )
            )
    return levels


# -- Order blocks ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OrderBlock:
    """The last opposite-colored candle immediately before a displacement
    candle (a true range at least `displacement_multiple` times the
    trailing ATR baseline) -- the standard SMC definition of the candle
    that supposedly absorbed the order flow behind the subsequent move.
    """

    bullish: bool
    index: int
    high: float
    low: float


def find_order_blocks(
    bars: Sequence[Bar],
    *,
    atr_period: int = 14,
    displacement_multiple: float = 1.5,
) -> list[OrderBlock]:
    if atr_period < 2:
        raise ValueError("atr_period must be >= 2")
    if displacement_multiple <= 1.0:
        raise ValueError("displacement_multiple must be > 1.0")

    order_blocks: list[OrderBlock] = []
    for i in range(atr_period + 1, len(bars)):
        # Baseline ATR excludes bar i itself, same as
        # AtrVolatilityBreakoutModule's own baseline/trigger split.
        baseline_atr = compute_atr(bars[:i], period=atr_period)
        if baseline_atr is None or baseline_atr <= 0:
            continue

        current, previous = bars[i], bars[i - 1]
        true_range = max(
            current.high - current.low,
            abs(current.high - previous.close),
            abs(current.low - previous.close),
        )
        if true_range < displacement_multiple * baseline_atr:
            continue

        displaced_up = current.close > current.open
        candidate = bars[i - 1]
        candidate_is_bearish = candidate.close < candidate.open
        candidate_is_bullish = candidate.close > candidate.open

        if displaced_up and candidate_is_bearish:
            order_blocks.append(
                OrderBlock(bullish=True, index=i - 1, high=candidate.high, low=candidate.low)
            )
        elif not displaced_up and candidate_is_bullish:
            order_blocks.append(
                OrderBlock(bullish=False, index=i - 1, high=candidate.high, low=candidate.low)
            )

    return order_blocks


# -- Liquidity sweeps ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LiquiditySweep:
    """A bar that wicks beyond a previously confirmed swing high/low but
    closes back inside it -- the classic stop-hunt ("turtle soup") pattern:
    the level's resting liquidity gets taken, then price reverses.
    """

    swept_high: bool
    index: int
    swept_level: float


def find_liquidity_sweeps(bars: Sequence[Bar], *, swing_arm: int = 2) -> list[LiquiditySweep]:
    if swing_arm < 1:
        raise ValueError("swing_arm must be >= 1")

    points = iter(find_all_swing_points(bars, arm=swing_arm))
    next_point = next(points, None)
    last_confirmed_high: float | None = None
    last_confirmed_low: float | None = None
    sweeps: list[LiquiditySweep] = []

    for i, bar in enumerate(bars):
        # A swing point at `p_index` is only confirmed once we've scanned
        # `swing_arm` bars past it -- same confirmation lag find_all_swing_points
        # itself relies on, just replayed here bar-by-bar as `i` advances.
        while next_point is not None and next_point[0] + swing_arm <= i:
            p_index, kind = next_point
            if kind == "high":
                last_confirmed_high = bars[p_index].high
            else:
                last_confirmed_low = bars[p_index].low
            next_point = next(points, None)

        if (
            last_confirmed_high is not None
            and bar.high > last_confirmed_high
            and bar.close < last_confirmed_high
        ):
            sweeps.append(LiquiditySweep(swept_high=True, index=i, swept_level=last_confirmed_high))
        if (
            last_confirmed_low is not None
            and bar.low < last_confirmed_low
            and bar.close > last_confirmed_low
        ):
            sweeps.append(LiquiditySweep(swept_high=False, index=i, swept_level=last_confirmed_low))

    return sweeps


class LiquiditySweepModule:
    """Fires when the *current* bar is itself a liquidity sweep: a stop hunt
    beyond a resting swing level that closes back inside is evidence of a
    reversal in the opposite direction of the sweep (SHORT after a high is
    swept, LONG after a low is swept). Confidence is the wick's penetration
    beyond the swept level, scaled by the bar's own range.
    """

    name = "liquidity_sweep"

    def __init__(self, *, swing_arm: int = 2) -> None:
        self._swing_arm = swing_arm

    def analyze(self, context: MarketContext) -> list[Evidence]:
        bars = context.bars
        if len(bars) < 2 * self._swing_arm + 2:
            return []

        sweeps = find_liquidity_sweeps(bars, swing_arm=self._swing_arm)
        if not sweeps or sweeps[-1].index != len(bars) - 1:
            return []

        sweep = sweeps[-1]
        current = bars[-1]
        bar_range = current.high - current.low
        if bar_range <= 0:
            return []

        if sweep.swept_high:
            penetration = current.high - sweep.swept_level
            direction = Direction.SHORT
        else:
            penetration = sweep.swept_level - current.low
            direction = Direction.LONG

        confidence = min(penetration / bar_range, 1.0)
        if confidence <= 0.0:
            return []

        return [
            Evidence(
                source_module=self.name,
                direction=direction,
                confidence=confidence,
                rationale={"swept_high": sweep.swept_high, "swept_level": sweep.swept_level},
            )
        ]


__all__ = [
    "EqualLevel",
    "FairValueGap",
    "FairValueGapModule",
    "LiquiditySweep",
    "LiquiditySweepModule",
    "OrderBlock",
    "find_equal_highs_lows",
    "find_fair_value_gaps",
    "find_liquidity_sweeps",
    "find_order_blocks",
]
