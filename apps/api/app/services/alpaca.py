from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import httpx

from ..config import Settings
from ..coordination import CoordinationBackend, get_coordination
from ..schemas import (
    AccountSnapshot,
    Bar,
    ExecutionOrder,
    MarketClock,
    MarketSnapshot,
    NewsItem,
    OptionContractSnapshot,
    Position,
    RiskGateResult,
    TradeProposal,
)
from .fixtures import (
    demo_account,
    demo_clock,
    demo_market,
    demo_news,
    demo_option_contracts,
)
from .indicators import compute_indicators


class AlpacaUnavailable(RuntimeError):
    pass


def _provider_failure(operation: str, exc: Exception) -> AlpacaUnavailable:
    message = str(exc).strip() or type(exc).__name__
    if "subscription does not permit querying recent SIP data" in message:
        message = (
            "the account cannot query recent SIP data; use "
            "ALPACA_DATA_FEED=iex or add an Alpaca SIP subscription"
        )
    return AlpacaUnavailable(f"Alpaca {operation} failed: {message}")


class AlpacaService:
    def __init__(
        self,
        settings: Settings,
        coordination: CoordinationBackend | None = None,
    ):
        self.settings = settings
        self.coordination = coordination or get_coordination()

    def _cache_ttl(self, ceiling: int) -> int:
        return max(1, min(self.settings.cache_ttl_seconds, ceiling))

    def _require_live(self) -> None:
        if not self.settings.alpaca_configured:
            raise AlpacaUnavailable("Alpaca paper credentials are not configured")
        if not self.settings.alpaca_paper or self.settings.live_trading_enabled:
            raise AlpacaUnavailable("SentinelAlpha only permits an explicitly configured paper client")

    def _trading_client(self):
        self._require_live()
        try:
            from alpaca.trading.client import TradingClient
        except ImportError as exc:
            raise AlpacaUnavailable("Install the 'alpaca' project extra to use live paper mode") from exc
        return TradingClient(
            self.settings.alpaca_api_key,
            self.settings.alpaca_secret_key,
            paper=True,
            # Alpaca's public resource URL includes `/v2`, but the SDK appends
            # that API prefix itself and therefore requires the host root.
            url_override=self.settings.alpaca_trading_base_url,
        )

    def connection_status(self) -> dict[str, Any]:
        """Describe configuration and optionally validate paper credentials."""
        status: dict[str, Any] = {
            "configured": self.settings.alpaca_configured,
            "paper": self.settings.alpaca_paper,
            "live_trading_enabled": self.settings.live_trading_enabled,
            "endpoint": self.settings.alpaca_trading_api_url,
            "connected": False,
            "options_execution_adapter": self.settings.alpaca_options_execution_adapter.upper(),
            "alpaca_cli_available": bool(shutil.which(self.settings.alpaca_cli_path)),
        }
        if not self.settings.alpaca_configured:
            status["message"] = "Add Alpaca paper credentials to the project .env file."
            return status
        try:
            account = self._trading_client().get_account()
        except Exception as exc:
            raise _provider_failure("connection check", exc) from exc
        status.update(
            {
                "connected": True,
                "account_id": str(account.id),
                "account_status": str(account.status).split(".")[-1],
                "message": "Authenticated against Alpaca paper trading.",
            }
        )
        return status

    def account(
        self,
        mode: str = "REPLAY",
        symbol: str = "AAPL",
        scenario: str = "risk_modification",
    ) -> AccountSnapshot:
        if mode == "REPLAY":
            return demo_account(symbol, scenario)
        cache_key = "account:paper"
        cached = self.coordination.get_json(cache_key)
        if cached is not None:
            return AccountSnapshot.model_validate(cached)
        client = self._trading_client()
        try:
            raw = client.get_account()
            positions_raw = client.get_all_positions()
        except Exception as exc:
            raise _provider_failure("account request", exc) from exc
        equity = float(raw.equity)
        positions = [
            Position(
                symbol=item.symbol,
                quantity=float(item.qty),
                market_value=float(item.market_value),
                avg_entry_price=float(item.avg_entry_price),
                current_price=float(item.current_price),
                unrealized_pl=float(item.unrealized_pl),
                unrealized_pl_pct=float(item.unrealized_plpc),
                weight=float(item.market_value) / equity if equity else 0,
            )
            for item in positions_raw
        ]
        last_equity = float(raw.last_equity or raw.equity)
        day_pl = equity - last_equity
        snapshot = AccountSnapshot(
            account_id=str(raw.id),
            status=str(raw.status),
            equity=equity,
            cash=float(raw.cash),
            buying_power=float(raw.buying_power),
            options_buying_power=(
                float(raw.options_buying_power)
                if raw.options_buying_power is not None
                else None
            ),
            options_approved_level=int(raw.options_approved_level or 0),
            options_trading_level=int(raw.options_trading_level or 0),
            day_pl=day_pl,
            day_pl_pct=day_pl / last_equity if last_equity else 0,
            portfolio_drawdown_pct=0,
            trades_today=0,
            positions=positions,
            open_orders=[],
            source="ALPACA_PAPER",
        )
        self.coordination.set_json(
            cache_key,
            snapshot.model_dump(mode="json"),
            self._cache_ttl(10),
        )
        return snapshot

    def clock(self, mode: str = "REPLAY") -> MarketClock:
        if mode == "REPLAY":
            return demo_clock()
        cache_key = "market-clock:paper"
        cached = self.coordination.get_json(cache_key)
        if cached is not None:
            return MarketClock.model_validate(cached)
        try:
            raw = self._trading_client().get_clock()
        except Exception as exc:
            raise _provider_failure("market clock request", exc) from exc
        clock = MarketClock(
            is_open=raw.is_open,
            timestamp=raw.timestamp,
            next_open=raw.next_open,
            next_close=raw.next_close,
            source="ALPACA_PAPER",
        )
        self.coordination.set_json(
            cache_key,
            clock.model_dump(mode="json"),
            self._cache_ttl(5),
        )
        return clock

    def market(self, symbol: str, mode: str = "REPLAY", scenario: str = "risk_modification") -> MarketSnapshot:
        if mode == "REPLAY":
            return demo_market(symbol, scenario)
        cache_key = f"market:{symbol}:day:{self.settings.alpaca_data_feed}"
        cached = self.coordination.get_json(cache_key)
        if cached is not None:
            return MarketSnapshot.model_validate(cached)
        self._require_live()
        try:
            from alpaca.data.enums import DataFeed
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest, StockLatestTradeRequest
            from alpaca.data.timeframe import TimeFrame
        except ImportError as exc:
            raise AlpacaUnavailable("Install the 'alpaca' project extra to use live paper mode") from exc
        client = StockHistoricalDataClient(self.settings.alpaca_api_key, self.settings.alpaca_secret_key)
        feed = DataFeed(self.settings.alpaca_data_feed)
        end = datetime.now(timezone.utc)
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=end - timedelta(days=180),
            end=end,
            limit=100,
            feed=feed,
        )
        try:
            response = client.get_stock_bars(request)
            latest = client.get_stock_latest_trade(
                StockLatestTradeRequest(symbol_or_symbols=symbol, feed=feed)
            )[symbol]
        except Exception as exc:
            raise _provider_failure("market data request", exc) from exc
        provider_bars = response.data.get(symbol, [])
        if not provider_bars:
            raise AlpacaUnavailable(
                f"Alpaca market data request returned no {self.settings.alpaca_data_feed.upper()} bars for {symbol}"
            )
        bars = [
            Bar(
                timestamp=item.timestamp,
                open=float(item.open),
                high=float(item.high),
                low=float(item.low),
                close=float(item.close),
                volume=int(item.volume),
            )
            for item in provider_bars
        ]
        indicators = compute_indicators(bars)
        snapshot = MarketSnapshot(
            symbol=symbol,
            price=float(latest.price),
            change_pct=indicators.daily_return,
            as_of=latest.timestamp,
            source="ALPACA_PAPER",
            bars=bars,
            indicators=indicators,
        )
        self.coordination.set_json(
            cache_key,
            snapshot.model_dump(mode="json"),
            self._cache_ttl(30),
        )
        return snapshot

    def news(self, symbol: str, mode: str = "REPLAY", scenario: str = "risk_modification") -> list[NewsItem]:
        if mode == "REPLAY":
            return demo_news(symbol, scenario)
        cache_key = f"news:{symbol}"
        cached = self.coordination.get_json(cache_key)
        if cached is not None:
            return [NewsItem.model_validate(item) for item in cached.get("items", [])]
        self._require_live()
        headers = {
            "APCA-API-KEY-ID": self.settings.alpaca_api_key or "",
            "APCA-API-SECRET-KEY": self.settings.alpaca_secret_key or "",
        }
        try:
            with httpx.Client(timeout=10) as client:
                response = client.get(
                    "https://data.alpaca.markets/v1beta1/news",
                    headers=headers,
                    params={"symbols": symbol, "limit": 12, "sort": "desc"},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise _provider_failure("news request", exc) from exc
        items = []
        for raw in response.json().get("news", []):
            text = f"{raw.get('headline', '')} {raw.get('summary', '')}".lower()
            positive = sum(word in text for word in ["beats", "raises", "growth", "strong", "upgrade"])
            negative = sum(word in text for word in ["misses", "cuts", "weak", "downgrade", "risk"])
            sentiment = max(-1, min(1, (positive - negative) / 3))
            items.append(
                NewsItem(
                    id=str(raw.get("id", uuid4())),
                    headline=raw.get("headline", "Untitled market update"),
                    summary=raw.get("summary", ""),
                    source=raw.get("source", "Alpaca News"),
                    published_at=datetime.fromisoformat(raw["created_at"].replace("Z", "+00:00")),
                    sentiment=sentiment,
                    relevance=1.0 if symbol in raw.get("symbols", []) else 0.6,
                    corroborated=False,
                    information_risk=["single_source"] if len(items) == 0 else [],
                )
            )
        result = items or demo_news(symbol, "agent_soc")
        self.coordination.set_json(
            cache_key,
            {"items": [item.model_dump(mode="json") for item in result]},
            self._cache_ttl(60),
        )
        return result

    def option_contracts(
        self,
        symbol: str,
        market_price: float,
        mode: str = "REPLAY",
    ) -> list[OptionContractSnapshot]:
        if mode == "REPLAY":
            return demo_option_contracts(symbol, market_price)
        cache_key = f"options:{symbol}:{round(market_price, 2)}:{self.settings.alpaca_options_feed}"
        cached = self.coordination.get_json(cache_key)
        if cached is not None:
            return [
                OptionContractSnapshot.model_validate(item)
                for item in cached.get("contracts", [])
            ]
        client = self._trading_client()
        try:
            from alpaca.data.enums import OptionsFeed
            from alpaca.data.historical.option import OptionHistoricalDataClient
            from alpaca.data.requests import OptionLatestQuoteRequest
            from alpaca.trading.enums import ContractType
            from alpaca.trading.requests import GetOptionContractsRequest
        except ImportError as exc:
            raise AlpacaUnavailable(
                "Install the 'alpaca' project extra to load option contracts"
            ) from exc

        today = datetime.now(timezone.utc).date()
        request = GetOptionContractsRequest(
            underlying_symbols=[symbol],
            type=ContractType.PUT,
            expiration_date_gte=today + timedelta(days=self.settings.hedge_min_dte),
            expiration_date_lte=today + timedelta(days=self.settings.hedge_max_dte),
            strike_price_gte=str(
                round(market_price * (1 - self.settings.hedge_max_otm_pct), 2)
            ),
            strike_price_lte=str(round(market_price, 2)),
            limit=500,
        )
        try:
            response = client.get_option_contracts(request)
            provider_contracts = list(response.option_contracts)
            if not provider_contracts:
                return []
            data_client = OptionHistoricalDataClient(
                self.settings.alpaca_api_key,
                self.settings.alpaca_secret_key,
            )
            feed = OptionsFeed(self.settings.alpaca_options_feed)
            quotes = data_client.get_option_latest_quote(
                OptionLatestQuoteRequest(
                    symbol_or_symbols=[item.symbol for item in provider_contracts],
                    feed=feed,
                )
            )
        except Exception as exc:
            raise _provider_failure("option-chain request", exc) from exc

        contracts: list[OptionContractSnapshot] = []
        for item in provider_contracts:
            quote = quotes.get(item.symbol)
            if quote is None or float(quote.ask_price or 0) <= 0:
                continue
            bid = max(0.0, float(quote.bid_price or 0))
            ask = float(quote.ask_price)
            contracts.append(
                OptionContractSnapshot(
                    symbol=item.symbol,
                    underlying_symbol=item.underlying_symbol,
                    option_type="PUT",
                    expiration_date=item.expiration_date,
                    strike_price=float(item.strike_price),
                    multiplier=int(float(item.size or 100)),
                    tradable=bool(item.tradable),
                    open_interest=(
                        int(float(item.open_interest))
                        if item.open_interest is not None
                        else None
                    ),
                    bid_price=bid,
                    ask_price=ask,
                    mid_price=max(0.01, round((bid + ask) / 2, 4)),
                    quote_as_of=quote.timestamp,
                    source="ALPACA_PAPER",
                )
            )
        self.coordination.set_json(
            cache_key,
            {"contracts": [item.model_dump(mode="json") for item in contracts]},
            self._cache_ttl(20),
        )
        return contracts

    def submit(
        self,
        proposal: TradeProposal,
        gate: RiskGateResult,
        equity: float,
        mode: str,
    ) -> ExecutionOrder:
        now = datetime.now(timezone.utc)
        client_order_id = f"sa-{proposal.workflow_run_id[:12]}-{proposal.symbol}-{proposal.side}".lower()
        notional = (
            round(proposal.requested_notional or 0, 2)
            if proposal.instrument_type == "OPTION"
            else round(equity * gate.approved_position_pct, 2)
        )
        if mode == "REPLAY":
            token = uuid4().hex[:12]
            plan = proposal.hedge_plan
            return ExecutionOrder(
                id=f"ord-{token}",
                provider_order_id=f"sim-paper-{token}",
                client_order_id=client_order_id,
                workflow_run_id=proposal.workflow_run_id,
                symbol=proposal.symbol,
                side=proposal.side,
                notional=notional,
                quantity=plan.contracts if plan else None,
                status="filled",
                execution_mode="SIMULATED_PAPER",
                submitted_at=now,
                filled_at=now,
                risk_decision=gate.decision,
                instrument_type=proposal.instrument_type,
                underlying_symbol=proposal.underlying_symbol,
                order_type="limit" if proposal.instrument_type == "OPTION" else "market",
                limit_price=plan.limit_price if plan else None,
                position_intent=proposal.position_intent,
                execution_interface="SIMULATED_REPLAY",
            )

        if proposal.instrument_type == "OPTION":
            return self._submit_option_cli(
                proposal,
                gate,
                client_order_id,
                notional,
                now,
            )

        client = self._trading_client()
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        request = MarketOrderRequest(
            symbol=proposal.symbol,
            notional=notional,
            side=OrderSide.BUY if proposal.side == "BUY" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            client_order_id=client_order_id,
        )
        try:
            raw = client.submit_order(order_data=request)
        except Exception as exc:
            raise _provider_failure("paper order submission", exc) from exc
        self.coordination.delete("account:paper")
        return ExecutionOrder(
            id=f"ord-{uuid4().hex[:12]}",
            provider_order_id=str(raw.id),
            client_order_id=client_order_id,
            workflow_run_id=proposal.workflow_run_id,
            symbol=proposal.symbol,
            side=proposal.side,
            notional=notional,
            quantity=float(raw.qty) if raw.qty else None,
            status=str(raw.status).split(".")[-1].lower(),
            execution_mode="ALPACA_PAPER",
            submitted_at=raw.submitted_at or now,
            filled_at=raw.filled_at,
            risk_decision=gate.decision,
            instrument_type="EQUITY",
            execution_interface="ALPACA_SDK",
        )

    def _submit_option_cli(
        self,
        proposal: TradeProposal,
        gate: RiskGateResult,
        client_order_id: str,
        notional: float,
        now: datetime,
    ) -> ExecutionOrder:
        self._require_live()
        plan = proposal.hedge_plan
        if not plan or not plan.contract or not plan.limit_price or plan.contracts < 1:
            raise AlpacaUnavailable("Option proposal is missing an executable hedge plan")
        executable = shutil.which(self.settings.alpaca_cli_path)
        if executable is None:
            raise AlpacaUnavailable(
                "Alpaca CLI is required for option execution. Install it with "
                "'go install github.com/alpacahq/cli/cmd/alpaca@latest' or set ALPACA_CLI_PATH."
            )
        command = [
            executable,
            "order",
            "submit",
            "--symbol",
            plan.contract.symbol,
            "--side",
            "buy",
            "--qty",
            str(plan.contracts),
            "--type",
            "limit",
            "--limit-price",
            f"{plan.limit_price:.2f}",
            "--time-in-force",
            "day",
            "--position-intent",
            "buy_to_open",
            "--client-order-id",
            client_order_id,
        ]
        environment = os.environ.copy()
        environment.update(
            {
                "ALPACA_API_KEY": self.settings.alpaca_api_key or "",
                "ALPACA_SECRET_KEY": self.settings.alpaca_secret_key or "",
                "ALPACA_LIVE_TRADE": "false",
                "ALPACA_OUTPUT": "json",
                "ALPACA_QUIET": "true",
            }
        )
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                env=environment,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise _provider_failure("CLI option order submission", exc) from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip() or "CLI returned a non-zero status"
            raise AlpacaUnavailable(
                f"Alpaca CLI option order submission failed: {detail[:500]}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise AlpacaUnavailable(
                "Alpaca CLI returned an unexpected non-JSON order response"
            ) from exc
        raw = payload.get("data", payload)
        provider_order_id = str(raw.get("id") or raw.get("order_id") or "")
        if not provider_order_id:
            raise AlpacaUnavailable("Alpaca CLI response did not contain an order ID")
        self.coordination.delete("account:paper")
        return ExecutionOrder(
            id=f"ord-{uuid4().hex[:12]}",
            provider_order_id=provider_order_id,
            client_order_id=client_order_id,
            workflow_run_id=proposal.workflow_run_id,
            symbol=plan.contract.symbol,
            side="BUY",
            notional=notional,
            quantity=plan.contracts,
            status=str(raw.get("status") or "accepted").split(".")[-1].lower(),
            execution_mode="ALPACA_PAPER",
            submitted_at=now,
            filled_at=None,
            risk_decision=gate.decision,
            instrument_type="OPTION",
            underlying_symbol=proposal.underlying_symbol,
            order_type="limit",
            limit_price=plan.limit_price,
            position_intent="BUY_TO_OPEN",
            execution_interface="ALPACA_CLI",
        )

    def provider_orders(self) -> list[dict[str, Any]]:
        client = self._trading_client()
        try:
            orders = client.get_orders()
        except Exception as exc:
            raise _provider_failure("orders request", exc) from exc
        return [order.model_dump(mode="json") for order in orders]

    def cancel_provider_order(self, provider_order_id: str) -> None:
        try:
            self._trading_client().cancel_order_by_id(provider_order_id)
        except Exception as exc:
            raise _provider_failure("order cancellation", exc) from exc
        self.coordination.delete("account:paper")
