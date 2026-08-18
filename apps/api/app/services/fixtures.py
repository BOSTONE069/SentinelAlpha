from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

from ..schemas import (
    AccountSnapshot,
    Bar,
    MarketClock,
    MarketSnapshot,
    NewsItem,
    OptionContractSnapshot,
    Position,
)
from .indicators import compute_indicators


BASE_PRICES = {
    "AAPL": 228.40,
    "NVDA": 183.20,
    "MSFT": 522.10,
    "TSLA": 311.70,
    "AMZN": 238.80,
    "META": 794.30,
}


def demo_bars(symbol: str, scenario: str = "risk_modification", count: int = 90) -> list[Bar]:
    now = datetime.now(timezone.utc)
    target = BASE_PRICES.get(symbol, 176.20)
    bars: list[Bar] = []
    stale_offset = timedelta(minutes=12) if scenario == "agent_soc" else timedelta(0)
    for index in range(count):
        days_ago = count - 1 - index
        trend = (index / (count - 1)) * (target * 0.16)
        wave = math.sin(index / 4.7) * target * 0.008
        close = target * 0.84 + trend + wave
        if scenario == "information_risk":
            close = target * 0.93 + (index / (count - 1)) * target * 0.07 + wave * 0.5
        if scenario == "agent_soc":
            close = target * 0.98 + math.sin(index / 2.8) * target * 0.015
        if scenario == "portfolio_protection":
            downtrend = (index / (count - 1)) * (target * 0.18)
            close = target * 1.18 - downtrend + math.sin(index / 2.1) * target * 0.018
        open_price = close * (1 - 0.002 * math.sin(index))
        high = max(open_price, close) * 1.005
        low = min(open_price, close) * 0.995
        volume = int(42_000_000 + math.sin(index / 3) * 5_000_000)
        if index == count - 1 and scenario == "risk_modification":
            volume = 65_000_000
        bars.append(
            Bar(
                timestamp=now - timedelta(days=days_ago) - stale_offset,
                open=round(open_price, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close, 2),
                volume=volume,
            )
        )
    return bars


def demo_market(symbol: str, scenario: str = "risk_modification") -> MarketSnapshot:
    bars = demo_bars(symbol, scenario)
    indicators = compute_indicators(bars)
    return MarketSnapshot(
        symbol=symbol,
        price=bars[-1].close,
        change_pct=indicators.daily_return,
        as_of=bars[-1].timestamp,
        source="DEMO_REPLAY",
        bars=bars,
        indicators=indicators,
    )


def demo_news(symbol: str, scenario: str = "risk_modification") -> list[NewsItem]:
    now = datetime.now(timezone.utc)
    if scenario == "information_risk":
        return [
            NewsItem(
                id="news-spike-1",
                headline=f"{symbol} tipped for a historic breakout after unnamed source claim",
                summary="A single report cites an unnamed source and uses unusually promotional language.",
                source="Market Pulse Wire",
                published_at=now - timedelta(minutes=18),
                sentiment=0.96,
                relevance=0.94,
                corroborated=False,
                information_risk=["sensational_language", "single_unconfirmed_narrative"],
            ),
            NewsItem(
                id="news-spike-2",
                headline=f"Analysts urge caution on unverified {symbol} report",
                summary="A separate desk says it cannot corroborate the reported catalyst.",
                source="Capital Desk",
                published_at=now - timedelta(minutes=12),
                sentiment=-0.45,
                relevance=0.88,
                corroborated=True,
                information_risk=["contradictory_narrative"],
            ),
            NewsItem(
                id="news-spike-3",
                headline=f"Social discussion around {symbol} accelerates",
                summary="Discussion volume rose sharply without a corresponding regulatory filing.",
                source="Signal Monitor",
                published_at=now - timedelta(minutes=7),
                sentiment=0.75,
                relevance=0.72,
                corroborated=False,
                information_risk=["sentiment_spike", "limited_corroboration"],
            ),
        ]
    if scenario == "agent_soc":
        return [
            NewsItem(
                id="news-soc-1",
                headline=f"Routine market update for {symbol}",
                summary="No material company-specific catalyst was identified.",
                source="Market Brief",
                published_at=now - timedelta(hours=5),
                sentiment=0.04,
                relevance=0.55,
                corroborated=True,
                information_risk=["stale_context"],
            )
        ]
    if scenario == "portfolio_protection":
        return [
            NewsItem(
                id="news-hedge-1",
                headline=f"{symbol} outlook softens as sector demand estimates decline",
                summary="Two independent desks reduced near-term estimates and flagged weaker pricing.",
                source="Capital Desk",
                published_at=now - timedelta(minutes=22),
                sentiment=-0.72,
                relevance=0.96,
                corroborated=True,
            ),
            NewsItem(
                id="news-hedge-2",
                headline=f"Options volatility rises around {symbol}",
                summary="Put demand and implied volatility increased as investors sought downside protection.",
                source="Exchange Monitor",
                published_at=now - timedelta(minutes=41),
                sentiment=-0.48,
                relevance=0.91,
                corroborated=True,
            ),
            NewsItem(
                id="news-hedge-3",
                headline="Technology sector breadth deteriorates",
                summary="Fewer large-cap technology shares remain above their medium-term trend.",
                source="Market Ledger",
                published_at=now - timedelta(hours=1),
                sentiment=-0.55,
                relevance=0.78,
                corroborated=True,
            ),
        ]
    return [
        NewsItem(
            id="news-demo-1",
            headline=f"{symbol} demand outlook strengthens into next quarter",
            summary="Channel checks point to resilient demand and improving product mix.",
            source="Market Ledger",
            published_at=now - timedelta(minutes=34),
            sentiment=0.72,
            relevance=0.94,
            corroborated=True,
        ),
        NewsItem(
            id="news-demo-2",
            headline=f"Two research desks lift {symbol} estimates",
            summary="Independent research teams raised estimates while noting valuation risk.",
            source="Capital Desk",
            published_at=now - timedelta(hours=1, minutes=12),
            sentiment=0.64,
            relevance=0.91,
            corroborated=True,
        ),
        NewsItem(
            id="news-demo-3",
            headline=f"Options activity increases around {symbol}",
            summary="Volume rose above its recent average, though direction remains mixed.",
            source="Exchange Monitor",
            published_at=now - timedelta(hours=2),
            sentiment=0.18,
            relevance=0.76,
            corroborated=True,
        ),
        NewsItem(
            id="news-demo-4",
            headline=f"Valuation remains a watch item for {symbol}",
            summary="A cautious note says the current multiple leaves less room for execution misses.",
            source="Northstar Research",
            published_at=now - timedelta(hours=3),
            sentiment=-0.28,
            relevance=0.84,
            corroborated=True,
        ),
    ]


def demo_account(
    symbol: str = "AAPL", scenario: str = "risk_modification"
) -> AccountSnapshot:
    if scenario == "portfolio_protection":
        current_price = BASE_PRICES.get(symbol, 176.20)
        primary_quantity = 100.0
        primary_value = round(primary_quantity * current_price, 2)
        positions = [
            Position(
                symbol=symbol,
                quantity=primary_quantity,
                market_value=primary_value,
                avg_entry_price=current_price * 1.08,
                current_price=current_price,
                unrealized_pl=-primary_value * 0.074,
                unrealized_pl_pct=-0.074,
                weight=primary_value / 100_000,
            ),
            Position(
                symbol="MSFT",
                quantity=30,
                market_value=15_663,
                avg_entry_price=548.20,
                current_price=522.10,
                unrealized_pl=-783,
                unrealized_pl_pct=-0.0476,
                weight=0.15663,
            ),
            Position(
                symbol="GOOGL",
                quantity=55,
                market_value=10_450,
                avg_entry_price=198.40,
                current_price=190.00,
                unrealized_pl=-462,
                unrealized_pl_pct=-0.0423,
                weight=0.1045,
            ),
        ]
        return AccountSnapshot(
            account_id="paper-hedge-demo-01",
            status="ACTIVE",
            equity=100_000,
            cash=32_500,
            buying_power=65_000,
            options_buying_power=25_000,
            options_approved_level=3,
            options_trading_level=3,
            day_pl=-2_180,
            day_pl_pct=-0.0218,
            portfolio_drawdown_pct=0.061,
            trades_today=2,
            positions=positions,
            open_orders=[],
            source="DEMO_REPLAY",
        )
    position_candidates = [
        Position(
            symbol=symbol,
            quantity=26.27,
            market_value=6000,
            avg_entry_price=211.80,
            current_price=BASE_PRICES.get(symbol, 176.20),
            unrealized_pl=436.70,
            unrealized_pl_pct=0.0785,
            weight=0.06,
        ),
        Position(
            symbol="MSFT",
            quantity=11.49,
            market_value=6000,
            avg_entry_price=487.30,
            current_price=522.10,
            unrealized_pl=399.85,
            unrealized_pl_pct=0.0714,
            weight=0.06,
        ),
        Position(
            symbol="NVDA",
            quantity=43.67,
            market_value=8000,
            avg_entry_price=168.40,
            current_price=183.20,
            unrealized_pl=646.32,
            unrealized_pl_pct=0.0879,
            weight=0.08,
        ),
    ]
    positions = list({position.symbol: position for position in reversed(position_candidates)}.values())
    return AccountSnapshot(
        account_id="paper-demo-01",
        status="ACTIVE",
        equity=100_000,
        cash=63_420,
        buying_power=126_840,
        day_pl=842.18,
        day_pl_pct=0.0085,
        portfolio_drawdown_pct=0.012,
        trades_today=3,
        positions=positions,
        open_orders=[],
        source="DEMO_REPLAY",
    )


def demo_option_contracts(
    symbol: str, market_price: float
) -> list[OptionContractSnapshot]:
    now = datetime.now(timezone.utc)
    expirations = [now.date() + timedelta(days=24), now.date() + timedelta(days=31)]
    target = round((market_price * 0.95) / 5) * 5
    contracts: list[OptionContractSnapshot] = []
    for expiry_index, expiration in enumerate(expirations):
        for strike_offset in (-5, 0, 5):
            strike = max(5.0, target + strike_offset)
            strike_code = f"{int(round(strike * 1000)):08d}"
            occ_symbol = f"{symbol}{expiration:%y%m%d}P{strike_code}"
            distance = abs(strike - target)
            mid = round(3.80 + expiry_index * 0.35 - distance * 0.08, 2)
            bid = round(max(0.05, mid - 0.12), 2)
            ask = round(mid + 0.12, 2)
            contracts.append(
                OptionContractSnapshot(
                    symbol=occ_symbol,
                    underlying_symbol=symbol,
                    option_type="PUT",
                    expiration_date=expiration,
                    strike_price=strike,
                    multiplier=100,
                    tradable=True,
                    open_interest=1_200 - int(distance * 40),
                    bid_price=bid,
                    ask_price=ask,
                    mid_price=round((bid + ask) / 2, 2),
                    quote_as_of=now,
                    source="DEMO_REPLAY",
                )
            )
    return contracts


def demo_clock() -> MarketClock:
    now = datetime.now(timezone.utc)
    return MarketClock(
        is_open=True,
        timestamp=now,
        next_open=now + timedelta(hours=16),
        next_close=now + timedelta(hours=5),
        source="DEMO_REPLAY",
    )
