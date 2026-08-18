from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("alpaca")

from alpaca.data.enums import DataFeed, OptionsFeed

from app.config import get_settings
from app.coordination import CoordinationBackend
from app.schemas import RiskGateResult
from app.services.alpaca import AlpacaService, AlpacaUnavailable
from app.services.agents import run_agent_council
from app.services.consensus import build_consensus
from app.services.fixtures import (
    demo_account,
    demo_market,
    demo_news,
    demo_option_contracts,
)
from app.services.hedging import build_protective_put_plan, hedge_trade_proposal
from app.services.risk import RiskControlState


def _live_settings():
    return replace(
        get_settings(),
        alpaca_api_key="test-paper-key",
        alpaca_secret_key="test-paper-secret",
        alpaca_paper=True,
        live_trading_enabled=False,
        alpaca_data_feed="iex",
    )


def _live_service() -> AlpacaService:
    settings = _live_settings()
    return AlpacaService(
        settings,
        CoordinationBackend(replace(settings, redis_url=None)),
    )


def test_live_market_requests_explicit_iex_feed(monkeypatch):
    captured = {}
    now = datetime.now(timezone.utc)
    provider_bars = [
        SimpleNamespace(
            timestamp=now - timedelta(days=60 - index),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            volume=1_000_000 + index,
        )
        for index in range(60)
    ]

    class FakeClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_stock_bars(self, request):
            captured["bar_calls"] = captured.get("bar_calls", 0) + 1
            captured["bars_feed"] = request.feed
            return SimpleNamespace(data={"AAPL": provider_bars})

        def get_stock_latest_trade(self, request):
            captured["trade_feed"] = request.feed
            return {"AAPL": SimpleNamespace(price=161.25, timestamp=now)}

    monkeypatch.setattr("alpaca.data.historical.StockHistoricalDataClient", FakeClient)

    service = _live_service()
    snapshot = service.market("AAPL", "LIVE")
    cached_snapshot = service.market("AAPL", "LIVE")

    assert captured == {
        "bar_calls": 1,
        "bars_feed": DataFeed.IEX,
        "trade_feed": DataFeed.IEX,
    }
    assert cached_snapshot == snapshot
    assert len(snapshot.bars) == 60
    assert snapshot.price == 161.25


def test_live_market_provider_error_becomes_controlled_unavailable(monkeypatch):
    class RejectingClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_stock_bars(self, _request):
            raise RuntimeError("subscription does not permit querying recent SIP data")

    monkeypatch.setattr(
        "alpaca.data.historical.StockHistoricalDataClient", RejectingClient
    )

    with pytest.raises(AlpacaUnavailable, match="ALPACA_DATA_FEED=iex"):
        _live_service().market("AAPL", "LIVE")


def test_live_option_contracts_merge_contract_metadata_with_indicative_quotes(
    monkeypatch,
):
    now = datetime.now(timezone.utc)
    expiration = now.date() + timedelta(days=30)
    contract = SimpleNamespace(
        symbol="NVDA260917P00175000",
        underlying_symbol="NVDA",
        expiration_date=expiration,
        strike_price="175",
        size="100",
        tradable=True,
        open_interest="912",
    )

    class FakeTradingClient:
        def get_option_contracts(self, request):
            assert request.underlying_symbols == ["NVDA"]
            return SimpleNamespace(option_contracts=[contract])

    class FakeOptionDataClient:
        def __init__(self, *_args, **_kwargs):
            pass

        def get_option_latest_quote(self, request):
            assert request.feed == OptionsFeed.INDICATIVE
            return {
                contract.symbol: SimpleNamespace(
                    bid_price=3.9,
                    ask_price=4.1,
                    timestamp=now,
                )
            }

    service = _live_service()
    monkeypatch.setattr(service, "_trading_client", lambda: FakeTradingClient())
    monkeypatch.setattr(
        "alpaca.data.historical.option.OptionHistoricalDataClient",
        FakeOptionDataClient,
    )

    contracts = service.option_contracts("NVDA", 183.2, "LIVE")

    assert len(contracts) == 1
    assert contracts[0].symbol == contract.symbol
    assert contracts[0].option_type == "PUT"
    assert contracts[0].mid_price == 4.0
    assert contracts[0].open_interest == 912


def test_live_option_submission_uses_alpaca_cli_with_idempotent_limit_order(
    monkeypatch,
):
    settings = _live_settings()
    service = _live_service()
    market = demo_market("NVDA", "portfolio_protection")
    news = demo_news("NVDA", "portfolio_protection")
    account = demo_account("NVDA", "portfolio_protection")
    decisions, _review = run_agent_council(
        settings, "RULES", "portfolio_protection", market, news, account
    )
    consensus = build_consensus(decisions)
    plan = build_protective_put_plan(
        "workflow-cli-test",
        market,
        news,
        account,
        decisions,
        demo_option_contracts("NVDA", market.price),
        RiskControlState(settings),
        "LIVE",
    )
    proposal = hedge_trade_proposal("workflow-cli-test", plan, consensus)
    assert proposal is not None
    gate = RiskGateResult(
        decision="APPROVE",
        requested_position_pct=plan.premium_pct_equity,
        approved_position_pct=plan.premium_pct_equity,
        checks=[],
        reasons=["test approval"],
    )
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"id": "provider-option-order", "status": "accepted"}),
            stderr="",
        )

    monkeypatch.setattr("app.services.alpaca.shutil.which", lambda _path: "/usr/bin/alpaca")
    monkeypatch.setattr("app.services.alpaca.subprocess.run", fake_run)

    order = service.submit(proposal, gate, account.equity, "LIVE")

    assert order.instrument_type == "OPTION"
    assert order.execution_interface == "ALPACA_CLI"
    assert order.provider_order_id == "provider-option-order"
    assert captured["command"][:3] == ["/usr/bin/alpaca", "order", "submit"]
    assert "--position-intent" in captured["command"]
    assert "--client-order-id" in captured["command"]
    assert captured["kwargs"]["check"] is False
    assert captured["kwargs"]["env"]["ALPACA_LIVE_TRADE"] == "false"
    assert captured["kwargs"]["env"]["ALPACA_OUTPUT"] == "json"
