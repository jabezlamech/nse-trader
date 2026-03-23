from pydantic import BaseModel
from typing import Optional, List
from enum import Enum


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


class Candle(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class PatternMatch(BaseModel):
    pattern_name: str
    signal: Signal
    confidence: float          # 0-100
    description: str
    candles_involved: int      # how many candles form this pattern


class BacktestResult(BaseModel):
    pattern_name: str
    signal: Signal
    total_occurrences: int
    successful_trades: int
    win_rate: float            # percentage
    avg_gain_pct: float        # average gain when successful
    avg_loss_pct: float        # average loss when failed
    expected_return: float     # win_rate * avg_gain - (1-win_rate) * avg_loss


class StockAnalysis(BaseModel):
    symbol: str
    company_name: str
    current_price: float
    change: float
    change_pct: float
    volume: float
    high_52w: float
    low_52w: float
    patterns_detected: List[PatternMatch]
    backtest_results: List[BacktestResult]
    overall_signal: Signal
    overall_confidence: float
    recommendation: str


class StockInfo(BaseModel):
    symbol: str
    name: str
    sector: Optional[str] = None
