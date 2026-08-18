import pytest

from app.config import (
    _alpaca_data_feed,
    _alpaca_options_execution_adapter,
    _alpaca_options_feed,
    _alpaca_trading_api_url,
    _database_url,
    get_settings,
)


def test_alpaca_endpoint_exposes_v2_but_sdk_receives_host_root():
    settings = get_settings()
    assert settings.alpaca_trading_api_url == "https://paper-api.alpaca.markets/v2"
    assert settings.alpaca_trading_base_url == "https://paper-api.alpaca.markets"
    assert settings.alpaca_data_feed == "iex"
    assert settings.alpaca_options_feed == "indicative"
    assert settings.alpaca_options_execution_adapter == "cli"


def test_relative_sqlite_database_is_resolved_against_api_root(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./sentinelalpha.db")
    assert _database_url().endswith("/apps/api/sentinelalpha.db")


def test_alpaca_data_feed_rejects_unknown_value(monkeypatch):
    monkeypatch.setenv("ALPACA_DATA_FEED", "free")
    with pytest.raises(ValueError, match="ALPACA_DATA_FEED must be one of"):
        _alpaca_data_feed()


def test_options_configuration_rejects_non_compliant_values(monkeypatch):
    monkeypatch.setenv("ALPACA_OPTIONS_FEED", "free")
    with pytest.raises(ValueError, match="indicative or opra"):
        _alpaca_options_feed()

    monkeypatch.setenv("ALPACA_OPTIONS_EXECUTION_ADAPTER", "sdk")
    with pytest.raises(ValueError, match="must be cli"):
        _alpaca_options_execution_adapter()


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "http://paper-api.alpaca.markets/v2",
        "https://api.alpaca.markets/v2",
        "https://paper-api.alpaca.markets/v1",
        "https://paper-api.alpaca.markets/v2/account",
        "https://paper-api.alpaca.markets:443/v2",
    ],
)
def test_alpaca_endpoint_rejects_non_paper_or_malformed_overrides(
    monkeypatch, unsafe_url
):
    monkeypatch.setenv("ALPACA_TRADING_API_URL", unsafe_url)
    with pytest.raises(ValueError, match="must be exactly"):
        _alpaca_trading_api_url()
