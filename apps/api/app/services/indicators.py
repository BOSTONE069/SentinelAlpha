from __future__ import annotations

import math
import statistics

from ..schemas import Bar, Indicators


def _ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    multiplier = 2 / (period + 1)
    output = [values[0]]
    for value in values[1:]:
        output.append((value * multiplier) + (output[-1] * (1 - multiplier)))
    return output


def _return(current: float, previous: float) -> float:
    return (current / previous - 1) if previous else 0.0


def compute_indicators(bars: list[Bar]) -> Indicators:
    if len(bars) < 50:
        raise ValueError("at least 50 bars are required")

    closes = [bar.close for bar in bars]
    volumes = [bar.volume for bar in bars]
    sma20 = statistics.fmean(closes[-20:])
    sma50 = statistics.fmean(closes[-50:])
    ema12_series = _ema(closes, 12)
    ema26_series = _ema(closes, 26)
    macd_series = [fast - slow for fast, slow in zip(ema12_series, ema26_series, strict=True)]
    macd_signal_series = _ema(macd_series, 9)

    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    gains = [max(change, 0) for change in changes[-14:]]
    losses = [abs(min(change, 0)) for change in changes[-14:]]
    avg_gain = statistics.fmean(gains)
    avg_loss = statistics.fmean(losses)
    rsi = 100.0 if avg_loss == 0 else 100 - (100 / (1 + avg_gain / avg_loss))

    true_ranges: list[float] = []
    for index, bar in enumerate(bars[-14:]):
        previous_close = bars[len(bars) - 15 + index].close
        true_ranges.append(
            max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close))
        )

    daily_returns = [_return(closes[index], closes[index - 1]) for index in range(1, len(closes))]
    volatility = statistics.stdev(daily_returns[-20:]) * math.sqrt(252)
    volume_mean = statistics.fmean(volumes[-20:])
    volume_std = statistics.pstdev(volumes[-20:]) or 1

    return Indicators(
        sma20=round(sma20, 2),
        sma50=round(sma50, 2),
        ema12=round(ema12_series[-1], 2),
        rsi14=round(rsi, 2),
        macd=round(macd_series[-1], 3),
        macd_signal=round(macd_signal_series[-1], 3),
        atr14=round(statistics.fmean(true_ranges), 2),
        daily_return=round(daily_returns[-1], 4),
        return_5d=round(_return(closes[-1], closes[-6]), 4),
        return_20d=round(_return(closes[-1], closes[-21]), 4),
        volatility_annualized=round(volatility, 4),
        volume_zscore=round((volumes[-1] - volume_mean) / volume_std, 2),
        support=round(min(closes[-20:]), 2),
        resistance=round(max(closes[-20:]), 2),
    )
