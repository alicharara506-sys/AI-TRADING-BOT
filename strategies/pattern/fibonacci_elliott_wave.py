from __future__ import annotations

from core.interfaces.types import Bar, Direction, Evidence, TradeSignal
from quant.price_action.elliott_wave import ImpulseWave, find_five_wave_impulse

# Typical Fibonacci ranges for a textbook impulse: wave 2 usually retraces
# 38.2%-78.6% of wave 1, wave 4 usually retraces 23.6%-50% of wave 3, and
# wave 3 is rarely the shortest -- it is at minimum as long as wave 1.
# These bands are a quality filter on top of the three hard structural
# rules already enforced by find_five_wave_impulse(): a candidate impulse
# that is structurally valid but has atypical ratios is silently rejected
# rather than traded on a shaky, non-textbook count.
_WAVE2_RETRACEMENT_RANGE = (0.382, 0.786)
_WAVE4_RETRACEMENT_RANGE = (0.236, 0.5)
_MIN_WAVE3_EXTENSION = 1.0
# Retracement ratios are computed from bar prices via division, so an exact
# boundary value (e.g. a clean 50% retracement) can land a hair outside its
# band due to ordinary floating-point rounding -- this tolerance absorbs
# that noise without meaningfully widening what counts as "typical".
_RATIO_EPSILON = 1e-9


class FibonacciElliottWaveStrategy:
    """Trades the completion of a structurally valid, Fibonacci-typical
    5-wave Elliott impulse.

    Once such an impulse finishes, Elliott Wave theory expects a 3-wave
    corrective move against it -- this strategy fades the completed 5th
    wave. "Structurally valid" combines two independently-verifiable
    things, not a subjective wave count:
      1. the three objective Elliott Wave rules
         (quant/price_action/elliott_wave.py::find_five_wave_impulse)
      2. wave 2 / wave 4 retracements and the wave 3 extension falling
         within their typical Fibonacci ranges (this module)

    Deliberately excludes the part of Elliott Wave analysis that is
    genuinely, famously subjective -- picking which swings belong to which
    wave count when more than one reading is plausible. This strategy only
    ever acts on the single, mechanically-detected candidate the shared
    swing-point primitive produces; if that candidate doesn't pass both
    checks, it is silently skipped rather than forced.
    """

    strategy_name = "fibonacci_elliott_wave"

    def __init__(self, *, swing_arm: int = 2, lookback: int = 300) -> None:
        if swing_arm < 1:
            raise ValueError("swing_arm must be >= 1")
        min_lookback = 2 * swing_arm + 12
        if lookback < min_lookback:
            raise ValueError(f"lookback must be >= {min_lookback}")
        self._swing_arm = swing_arm
        self._lookback = lookback
        self._bars: list[Bar] = []
        self._last_signaled_wave5_index: int | None = None

    def on_bar(self, bar: Bar) -> TradeSignal | None:
        self._bars.append(bar)
        if len(self._bars) > self._lookback:
            del self._bars[: len(self._bars) - self._lookback]

        impulse = find_five_wave_impulse(self._bars, swing_arm=self._swing_arm)
        if impulse is None:
            return None

        wave5_index = impulse.indices[5]
        if wave5_index == self._last_signaled_wave5_index:
            return None  # already signaled this exact impulse
        self._last_signaled_wave5_index = wave5_index

        if not self._has_typical_fibonacci_ratios(impulse):
            return None

        direction = Direction.SHORT if impulse.direction_up else Direction.LONG
        confidence = self._confidence(impulse)
        evidence = Evidence(
            source_module=self.strategy_name,
            direction=direction,
            confidence=confidence,
            rationale={
                "event": "elliott_wave5_completion",
                "impulse_direction_up": impulse.direction_up,
                "wave2_retracement": impulse.wave2_retracement,
                "wave4_retracement": impulse.wave4_retracement,
                "wave3_extension": impulse.wave3_extension,
            },
        )
        return TradeSignal(
            symbol=bar.symbol,
            direction=direction,
            combined_confidence=confidence,
            threshold=0.0,
            evidence=(evidence,),
        )

    def _has_typical_fibonacci_ratios(self, impulse: ImpulseWave) -> bool:
        wave2_low, wave2_high = _WAVE2_RETRACEMENT_RANGE
        wave4_low, wave4_high = _WAVE4_RETRACEMENT_RANGE
        eps = _RATIO_EPSILON
        return (
            wave2_low - eps <= impulse.wave2_retracement <= wave2_high + eps
            and wave4_low - eps <= impulse.wave4_retracement <= wave4_high + eps
            and impulse.wave3_extension >= _MIN_WAVE3_EXTENSION - eps
        )

    def _confidence(self, impulse: ImpulseWave) -> float:
        # Bounded geometric confidence: how centered each retracement sits
        # within its typical Fibonacci band -- the same "confidence scaled
        # by how textbook the pattern is" spirit FibonacciConfluenceModule
        # already uses for a single retracement level.
        wave2_score = _centeredness(impulse.wave2_retracement, _WAVE2_RETRACEMENT_RANGE)
        wave4_score = _centeredness(impulse.wave4_retracement, _WAVE4_RETRACEMENT_RANGE)
        return max(0.1, (wave2_score + wave4_score) / 2)


def _centeredness(value: float, band: tuple[float, float]) -> float:
    low, high = band
    center = (low + high) / 2
    half_width = (high - low) / 2
    return 1.0 - min(abs(value - center) / half_width, 1.0)


__all__ = ["FibonacciElliottWaveStrategy"]
