"""
Candlestick pattern detection engine.
Detects 20+ classic candlestick patterns and assigns BUY/SELL signals with confidence scores.
"""

import pandas as pd
import numpy as np
from typing import List
from models import PatternMatch, Signal


def _body_size(row) -> float:
    return abs(row["close"] - row["open"])


def _upper_shadow(row) -> float:
    return row["high"] - max(row["open"], row["close"])


def _lower_shadow(row) -> float:
    return min(row["open"], row["close"]) - row["low"]


def _candle_range(row) -> float:
    return row["high"] - row["low"]


def _is_bullish(row) -> bool:
    return row["close"] > row["open"]


def _is_bearish(row) -> bool:
    return row["close"] < row["open"]


def _avg_body(df: pd.DataFrame, n: int = 10) -> float:
    bodies = df.apply(_body_size, axis=1)
    return bodies.rolling(n).mean().iloc[-1]


# ─── Single-candle patterns ────────────────────────────────────────────────────

def detect_doji(df: pd.DataFrame) -> List[PatternMatch]:
    patterns = []
    avg = _avg_body(df)
    c = df.iloc[-1]
    body = _body_size(c)
    cr = _candle_range(c)

    if cr == 0:
        return patterns

    if body <= 0.05 * cr and cr > 0:
        upper = _upper_shadow(c)
        lower = _lower_shadow(c)

        if upper > 2 * lower:
            patterns.append(PatternMatch(
                pattern_name="Gravestone Doji",
                signal=Signal.SELL,
                confidence=72,
                description="Long upper shadow with tiny body at bottom. Bearish reversal signal — sellers rejected higher prices.",
                candles_involved=1
            ))
        elif lower > 2 * upper:
            patterns.append(PatternMatch(
                pattern_name="Dragonfly Doji",
                signal=Signal.BUY,
                confidence=72,
                description="Long lower shadow with tiny body at top. Bullish reversal signal — buyers rejected lower prices.",
                candles_involved=1
            ))
        else:
            patterns.append(PatternMatch(
                pattern_name="Doji",
                signal=Signal.NEUTRAL,
                confidence=55,
                description="Open and close nearly equal. Market indecision — watch for breakout confirmation.",
                candles_involved=1
            ))
    return patterns


def detect_hammer(df: pd.DataFrame) -> List[PatternMatch]:
    patterns = []
    if len(df) < 3:
        return patterns

    c = df.iloc[-1]
    body = _body_size(c)
    cr = _candle_range(c)
    lower = _lower_shadow(c)
    upper = _upper_shadow(c)

    if cr == 0 or body == 0:
        return patterns

    # Hammer: small body at top, long lower shadow (>2x body), small upper shadow
    if lower >= 2 * body and upper <= 0.3 * body and body > 0:
        # Confirm downtrend in previous candles
        prev_closes = df["close"].iloc[-4:-1]
        in_downtrend = prev_closes.iloc[0] > prev_closes.iloc[-1]

        if in_downtrend:
            patterns.append(PatternMatch(
                pattern_name="Hammer",
                signal=Signal.BUY,
                confidence=78,
                description="Small body with long lower shadow after downtrend. Bulls pushed price back up — bullish reversal signal.",
                candles_involved=1
            ))

    # Inverted Hammer: small body at bottom, long upper shadow
    if upper >= 2 * body and lower <= 0.3 * body and body > 0:
        prev_closes = df["close"].iloc[-4:-1]
        in_downtrend = prev_closes.iloc[0] > prev_closes.iloc[-1]

        if in_downtrend:
            patterns.append(PatternMatch(
                pattern_name="Inverted Hammer",
                signal=Signal.BUY,
                confidence=65,
                description="Long upper shadow after downtrend. Possible bullish reversal — confirm with next candle.",
                candles_involved=1
            ))

    # Shooting Star: long upper shadow at the top of an uptrend
    if upper >= 2 * body and lower <= 0.3 * body and body > 0:
        prev_closes = df["close"].iloc[-4:-1]
        in_uptrend = prev_closes.iloc[0] < prev_closes.iloc[-1]

        if in_uptrend:
            patterns.append(PatternMatch(
                pattern_name="Shooting Star",
                signal=Signal.SELL,
                confidence=76,
                description="Long upper shadow after uptrend. Bears rejected higher prices — bearish reversal signal.",
                candles_involved=1
            ))

    # Hanging Man: hammer shape but in uptrend
    if lower >= 2 * body and upper <= 0.3 * body and body > 0:
        prev_closes = df["close"].iloc[-4:-1]
        in_uptrend = prev_closes.iloc[0] < prev_closes.iloc[-1]

        if in_uptrend:
            patterns.append(PatternMatch(
                pattern_name="Hanging Man",
                signal=Signal.SELL,
                confidence=68,
                description="Hammer shape in uptrend. Sellers appeared at highs — potential bearish reversal.",
                candles_involved=1
            ))

    return patterns


def detect_marubozu(df: pd.DataFrame) -> List[PatternMatch]:
    patterns = []
    c = df.iloc[-1]
    body = _body_size(c)
    cr = _candle_range(c)

    if cr == 0:
        return patterns

    # Marubozu: body is ≥95% of full range (no/tiny shadows)
    if body >= 0.95 * cr:
        if _is_bullish(c):
            patterns.append(PatternMatch(
                pattern_name="Bullish Marubozu",
                signal=Signal.BUY,
                confidence=80,
                description="Full bullish candle with no shadows. Strong buying momentum — bulls in complete control.",
                candles_involved=1
            ))
        else:
            patterns.append(PatternMatch(
                pattern_name="Bearish Marubozu",
                signal=Signal.SELL,
                confidence=80,
                description="Full bearish candle with no shadows. Strong selling pressure — bears in complete control.",
                candles_involved=1
            ))
    return patterns


def detect_spinning_top(df: pd.DataFrame) -> List[PatternMatch]:
    patterns = []
    c = df.iloc[-1]
    body = _body_size(c)
    cr = _candle_range(c)
    upper = _upper_shadow(c)
    lower = _lower_shadow(c)

    if cr == 0:
        return patterns

    # Spinning top: small body (10-30% of range), long shadows on both sides
    if 0.05 * cr < body < 0.35 * cr and upper > body and lower > body:
        patterns.append(PatternMatch(
            pattern_name="Spinning Top",
            signal=Signal.NEUTRAL,
            confidence=50,
            description="Small body with long shadows on both sides. Market indecision — neither bulls nor bears in control.",
            candles_involved=1
        ))
    return patterns


# ─── Two-candle patterns ───────────────────────────────────────────────────────

def detect_engulfing(df: pd.DataFrame) -> List[PatternMatch]:
    patterns = []
    if len(df) < 2:
        return patterns

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    prev_body = _body_size(prev)
    curr_body = _body_size(curr)

    if prev_body == 0:
        return patterns

    # Bullish engulfing: prev bearish, curr bullish and engulfs prev
    if (_is_bearish(prev) and _is_bullish(curr) and
            curr["open"] <= prev["close"] and curr["close"] >= prev["open"] and
            curr_body > prev_body):
        patterns.append(PatternMatch(
            pattern_name="Bullish Engulfing",
            signal=Signal.BUY,
            confidence=82,
            description="Bullish candle completely engulfs prior bearish candle. Strong buying reversal — high reliability pattern.",
            candles_involved=2
        ))

    # Bearish engulfing: prev bullish, curr bearish and engulfs prev
    if (_is_bullish(prev) and _is_bearish(curr) and
            curr["open"] >= prev["close"] and curr["close"] <= prev["open"] and
            curr_body > prev_body):
        patterns.append(PatternMatch(
            pattern_name="Bearish Engulfing",
            signal=Signal.SELL,
            confidence=82,
            description="Bearish candle completely engulfs prior bullish candle. Strong selling reversal — high reliability pattern.",
            candles_involved=2
        ))

    return patterns


def detect_harami(df: pd.DataFrame) -> List[PatternMatch]:
    patterns = []
    if len(df) < 2:
        return patterns

    prev = df.iloc[-2]
    curr = df.iloc[-1]
    prev_body = _body_size(prev)
    curr_body = _body_size(curr)

    if prev_body == 0:
        return patterns

    # Harami: current candle's body fits inside previous candle's body
    prev_top = max(prev["open"], prev["close"])
    prev_bot = min(prev["open"], prev["close"])
    curr_top = max(curr["open"], curr["close"])
    curr_bot = min(curr["open"], curr["close"])

    if curr_top <= prev_top and curr_bot >= prev_bot and curr_body < 0.6 * prev_body:
        if _is_bearish(prev) and _is_bullish(curr):
            patterns.append(PatternMatch(
                pattern_name="Bullish Harami",
                signal=Signal.BUY,
                confidence=65,
                description="Small bullish candle inside a large bearish candle. Potential selling exhaustion — wait for confirmation.",
                candles_involved=2
            ))
        elif _is_bullish(prev) and _is_bearish(curr):
            patterns.append(PatternMatch(
                pattern_name="Bearish Harami",
                signal=Signal.SELL,
                confidence=65,
                description="Small bearish candle inside a large bullish candle. Potential buying exhaustion — wait for confirmation.",
                candles_involved=2
            ))
    return patterns


def detect_tweezer(df: pd.DataFrame) -> List[PatternMatch]:
    patterns = []
    if len(df) < 2:
        return patterns

    prev = df.iloc[-2]
    curr = df.iloc[-1]
    tol = (prev["high"] - prev["low"]) * 0.01  # 1% tolerance

    # Tweezer Top: both candles hit same high
    if abs(prev["high"] - curr["high"]) <= tol and _is_bullish(prev) and _is_bearish(curr):
        patterns.append(PatternMatch(
            pattern_name="Tweezer Top",
            signal=Signal.SELL,
            confidence=70,
            description="Two candles with matching highs — resistance confirmed at this level. Bearish reversal signal.",
            candles_involved=2
        ))

    # Tweezer Bottom: both candles hit same low
    if abs(prev["low"] - curr["low"]) <= tol and _is_bearish(prev) and _is_bullish(curr):
        patterns.append(PatternMatch(
            pattern_name="Tweezer Bottom",
            signal=Signal.BUY,
            confidence=70,
            description="Two candles with matching lows — support confirmed at this level. Bullish reversal signal.",
            candles_involved=2
        ))
    return patterns


def detect_piercing_dark_cloud(df: pd.DataFrame) -> List[PatternMatch]:
    patterns = []
    if len(df) < 2:
        return patterns

    prev = df.iloc[-2]
    curr = df.iloc[-1]
    prev_mid = (prev["open"] + prev["close"]) / 2

    # Piercing Line: large bearish prev, bullish curr opens below prev low and closes above midpoint
    if (_is_bearish(prev) and _is_bullish(curr) and
            curr["open"] < prev["low"] and curr["close"] > prev_mid and
            curr["close"] < prev["open"]):
        patterns.append(PatternMatch(
            pattern_name="Piercing Line",
            signal=Signal.BUY,
            confidence=74,
            description="Bullish candle pierces more than halfway into prior bearish candle. Buyers taking control — bullish reversal.",
            candles_involved=2
        ))

    # Dark Cloud Cover: large bullish prev, bearish curr opens above prev high and closes below midpoint
    if (_is_bullish(prev) and _is_bearish(curr) and
            curr["open"] > prev["high"] and curr["close"] < prev_mid and
            curr["close"] > prev["open"]):
        patterns.append(PatternMatch(
            pattern_name="Dark Cloud Cover",
            signal=Signal.SELL,
            confidence=74,
            description="Bearish candle closes below midpoint of prior bullish candle. Sellers taking control — bearish reversal.",
            candles_involved=2
        ))
    return patterns


# ─── Three-candle patterns ─────────────────────────────────────────────────────

def detect_morning_evening_star(df: pd.DataFrame) -> List[PatternMatch]:
    patterns = []
    if len(df) < 3:
        return patterns

    c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    c2_body = _body_size(c2)
    avg = _avg_body(df)

    # Morning Star: c1 bearish large, c2 small (star), c3 bullish closes above c1 midpoint
    c1_mid = (c1["open"] + c1["close"]) / 2
    if (_is_bearish(c1) and c2_body < 0.3 * _body_size(c1) and
            _is_bullish(c3) and c3["close"] > c1_mid):
        patterns.append(PatternMatch(
            pattern_name="Morning Star",
            signal=Signal.BUY,
            confidence=85,
            description="Three-candle bullish reversal: large bearish, small star, large bullish. One of the strongest buy signals.",
            candles_involved=3
        ))

    # Evening Star: c1 bullish large, c2 small (star), c3 bearish closes below c1 midpoint
    c1_mid_bull = (c1["open"] + c1["close"]) / 2
    if (_is_bullish(c1) and c2_body < 0.3 * _body_size(c1) and
            _is_bearish(c3) and c3["close"] < c1_mid_bull):
        patterns.append(PatternMatch(
            pattern_name="Evening Star",
            signal=Signal.SELL,
            confidence=85,
            description="Three-candle bearish reversal: large bullish, small star, large bearish. One of the strongest sell signals.",
            candles_involved=3
        ))
    return patterns


def detect_three_soldiers_crows(df: pd.DataFrame) -> List[PatternMatch]:
    patterns = []
    if len(df) < 3:
        return patterns

    c1, c2, c3 = df.iloc[-3], df.iloc[-2], df.iloc[-1]
    avg = _avg_body(df)

    # Three White Soldiers: 3 consecutive bullish candles with higher closes
    if (all(_is_bullish(c) for c in [c1, c2, c3]) and
            c2["close"] > c1["close"] and c3["close"] > c2["close"] and
            c2["open"] > c1["open"] and c3["open"] > c2["open"] and
            all(_body_size(c) > 0.5 * avg for c in [c1, c2, c3])):
        patterns.append(PatternMatch(
            pattern_name="Three White Soldiers",
            signal=Signal.BUY,
            confidence=88,
            description="Three consecutive strong bullish candles. Powerful uptrend continuation — strong buying momentum.",
            candles_involved=3
        ))

    # Three Black Crows: 3 consecutive bearish candles with lower closes
    if (all(_is_bearish(c) for c in [c1, c2, c3]) and
            c2["close"] < c1["close"] and c3["close"] < c2["close"] and
            c2["open"] < c1["open"] and c3["open"] < c2["open"] and
            all(_body_size(c) > 0.5 * avg for c in [c1, c2, c3])):
        patterns.append(PatternMatch(
            pattern_name="Three Black Crows",
            signal=Signal.SELL,
            confidence=88,
            description="Three consecutive strong bearish candles. Powerful downtrend continuation — strong selling pressure.",
            candles_involved=3
        ))
    return patterns


def detect_inside_outside_bar(df: pd.DataFrame) -> List[PatternMatch]:
    patterns = []
    if len(df) < 2:
        return patterns

    prev = df.iloc[-2]
    curr = df.iloc[-1]

    # Inside bar: current range is inside previous range
    if curr["high"] < prev["high"] and curr["low"] > prev["low"]:
        patterns.append(PatternMatch(
            pattern_name="Inside Bar",
            signal=Signal.NEUTRAL,
            confidence=60,
            description="Price consolidating inside prior candle's range. Breakout pending — trade the breakout direction.",
            candles_involved=2
        ))

    # Outside bar: current range engulfs previous range (different from engulfing - based on wick)
    if curr["high"] > prev["high"] and curr["low"] < prev["low"]:
        sig = Signal.BUY if _is_bullish(curr) else Signal.SELL
        patterns.append(PatternMatch(
            pattern_name="Outside Bar",
            signal=sig,
            confidence=65,
            description="Current candle's range engulfs previous. Volatile session — direction determined by close.",
            candles_involved=2
        ))
    return patterns


# ─── Main detector ─────────────────────────────────────────────────────────────

DETECTORS = [
    detect_doji,
    detect_hammer,
    detect_marubozu,
    detect_spinning_top,
    detect_engulfing,
    detect_harami,
    detect_tweezer,
    detect_piercing_dark_cloud,
    detect_morning_evening_star,
    detect_three_soldiers_crows,
    detect_inside_outside_bar,
]


def detect_all_patterns(df: pd.DataFrame) -> List[PatternMatch]:
    """Run all pattern detectors and return found patterns sorted by confidence."""
    if df is None or len(df) < 3:
        return []

    all_patterns = []
    for detector in DETECTORS:
        try:
            found = detector(df)
            all_patterns.extend(found)
        except Exception:
            pass

    # Sort by confidence descending
    all_patterns.sort(key=lambda p: p.confidence, reverse=True)
    return all_patterns


def compute_overall_signal(patterns: List[PatternMatch]) -> tuple:
    """Aggregate pattern signals into overall signal + confidence."""
    if not patterns:
        return Signal.NEUTRAL, 0.0

    buy_score = sum(p.confidence for p in patterns if p.signal == Signal.BUY)
    sell_score = sum(p.confidence for p in patterns if p.signal == Signal.SELL)
    neutral_score = sum(p.confidence for p in patterns if p.signal == Signal.NEUTRAL)

    total = buy_score + sell_score + neutral_score
    if total == 0:
        return Signal.NEUTRAL, 0.0

    if buy_score > sell_score and buy_score > neutral_score:
        return Signal.BUY, round(buy_score / total * 100, 1)
    elif sell_score > buy_score and sell_score > neutral_score:
        return Signal.SELL, round(sell_score / total * 100, 1)
    else:
        return Signal.NEUTRAL, round(neutral_score / total * 100, 1)


def build_recommendation(signal: Signal, confidence: float, patterns: List[PatternMatch]) -> str:
    """Build a human-readable recommendation string."""
    top_pattern = patterns[0].pattern_name if patterns else "No pattern"

    if signal == Signal.BUY:
        if confidence >= 70:
            return f"Strong BUY signal from {top_pattern}. Consider entering a long position with stop-loss below the recent low."
        else:
            return f"Moderate BUY signal from {top_pattern}. Wait for confirmation before entering — risk is elevated."
    elif signal == Signal.SELL:
        if confidence >= 70:
            return f"Strong SELL signal from {top_pattern}. Consider exiting longs or entering short with stop-loss above the recent high."
        else:
            return f"Moderate SELL signal from {top_pattern}. Watch for confirmation before acting — consider tightening stop-loss."
    else:
        return f"Market shows indecision ({top_pattern}). Wait for a clear directional candle before taking a position."
