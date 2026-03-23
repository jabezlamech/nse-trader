"""
Backtesting engine: tests each candlestick pattern on historical data
and computes win rate, avg gain/loss, and expected return.
"""

import pandas as pd
import numpy as np
from typing import List, Dict
from candle_patterns import DETECTORS, detect_all_patterns
from models import BacktestResult, Signal


# How many candles forward to check the trade outcome
FORWARD_CANDLES = 5

# Minimum % move to count as success
MIN_MOVE_PCT = 0.5


def _run_single_pattern_backtest(
    df: pd.DataFrame,
    detector_func,
    forward: int = FORWARD_CANDLES
) -> BacktestResult | None:
    """
    Slide a window over df, detect pattern at each bar, measure outcome.
    Returns BacktestResult or None if no occurrences found.
    """
    wins = 0
    losses = 0
    gain_list = []
    loss_list = []
    signal_type = None
    pattern_name = None

    window = max(10, forward + 3)

    for i in range(window, len(df) - forward):
        window_df = df.iloc[i - window:i + 1].copy()
        try:
            matches = detector_func(window_df)
        except Exception:
            continue

        if not matches:
            continue

        # Use the first detected match in this window
        match = matches[0]
        if signal_type is None:
            signal_type = match.signal
            pattern_name = match.pattern_name
        elif match.signal != signal_type:
            continue  # Skip if conflicting signals from same detector

        entry_price = df.iloc[i]["close"]
        future_slice = df.iloc[i + 1: i + 1 + forward]

        if future_slice.empty:
            continue

        if signal_type == Signal.BUY:
            best_price = future_slice["high"].max()
            move_pct = (best_price - entry_price) / entry_price * 100
        elif signal_type == Signal.SELL:
            worst_price = future_slice["low"].min()
            move_pct = (entry_price - worst_price) / entry_price * 100
        else:
            continue  # Skip neutral

        if move_pct >= MIN_MOVE_PCT:
            wins += 1
            gain_list.append(move_pct)
        else:
            losses += 1
            # Calculate adverse move
            if signal_type == Signal.BUY:
                adverse = (entry_price - future_slice["low"].min()) / entry_price * 100
            else:
                adverse = (future_slice["high"].max() - entry_price) / entry_price * 100
            loss_list.append(abs(adverse))

    total = wins + losses
    if total < 3 or pattern_name is None:
        return None

    win_rate = wins / total * 100
    avg_gain = float(np.mean(gain_list)) if gain_list else 0.0
    avg_loss = float(np.mean(loss_list)) if loss_list else 0.0
    expected_return = (win_rate / 100 * avg_gain) - ((1 - win_rate / 100) * avg_loss)

    return BacktestResult(
        pattern_name=pattern_name,
        signal=signal_type,
        total_occurrences=total,
        successful_trades=wins,
        win_rate=round(win_rate, 1),
        avg_gain_pct=round(avg_gain, 2),
        avg_loss_pct=round(avg_loss, 2),
        expected_return=round(expected_return, 2),
    )


def run_backtest(df: pd.DataFrame) -> List[BacktestResult]:
    """
    Run backtest for all pattern detectors over historical df.
    Returns list of BacktestResult sorted by win_rate descending.
    """
    results = []
    for detector in DETECTORS:
        result = _run_single_pattern_backtest(df, detector)
        if result is not None:
            results.append(result)

    results.sort(key=lambda r: r.win_rate, reverse=True)
    return results


def get_pattern_stats_summary(results: List[BacktestResult]) -> Dict:
    """Summarize backtest results into actionable stats."""
    if not results:
        return {}

    buy_results = [r for r in results if r.signal == Signal.BUY]
    sell_results = [r for r in results if r.signal == Signal.SELL]

    best_buy = max(buy_results, key=lambda r: r.win_rate) if buy_results else None
    best_sell = max(sell_results, key=lambda r: r.win_rate) if sell_results else None

    return {
        "total_patterns_tested": len(results),
        "best_buy_pattern": best_buy.pattern_name if best_buy else None,
        "best_buy_win_rate": best_buy.win_rate if best_buy else 0,
        "best_sell_pattern": best_sell.pattern_name if best_sell else None,
        "best_sell_win_rate": best_sell.win_rate if best_sell else 0,
        "avg_win_rate": round(sum(r.win_rate for r in results) / len(results), 1),
    }
