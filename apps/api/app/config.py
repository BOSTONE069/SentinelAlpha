from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv


_api_root = Path(__file__).resolve().parents[1]
for _root in (_api_root, *_api_root.parents):
    _candidate = _root / ".env"
    if _candidate.is_file():
        load_dotenv(_candidate, override=False)
        break


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _database_url() -> str:
    value = os.getenv("DATABASE_URL", "sqlite:///./sentinelalpha.db").strip()
    prefix = "sqlite:///./"
    if value.startswith(prefix):
        database_path = Path(__file__).resolve().parents[1] / value.removeprefix(prefix)
        return f"sqlite:///{database_path}"
    # Render and several other managed PostgreSQL providers expose a generic
    # connection string. Select psycopg 3 explicitly because that is the
    # PostgreSQL driver installed by this application.
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    return value


def _alpaca_trading_api_url() -> str:
    """Return the locked Alpaca paper REST v2 endpoint.

    The configured value includes `/v2` because that is the public REST API
    prefix. Alpaca-py's `url_override`, however, receives the host root through
    `Settings.alpaca_trading_base_url` so the SDK does not build `/v2/v2/...`.
    """
    raw = os.getenv(
        "ALPACA_TRADING_API_URL", "https://paper-api.alpaca.markets/v2"
    ).strip().rstrip("/")
    parsed = urlparse(raw)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "paper-api.alpaca.markets"
        or parsed.port is not None
        or parsed.path.rstrip("/") != "/v2"
        or parsed.params
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
    ):
        raise ValueError(
            "ALPACA_TRADING_API_URL must be exactly "
            "https://paper-api.alpaca.markets/v2"
        )
    return "https://paper-api.alpaca.markets/v2"


def _alpaca_data_feed() -> str:
    """Return a supported Alpaca equity data feed.

    IEX is the safe default for paper accounts without a paid SIP market-data
    subscription. Keeping the value explicit prevents alpaca-py defaults from
    selecting a feed that the configured account cannot query.
    """
    value = os.getenv("ALPACA_DATA_FEED", "iex").strip().lower()
    supported = {"iex", "sip", "delayed_sip", "otc", "boats", "overnight"}
    if value not in supported:
        choices = ", ".join(sorted(supported))
        raise ValueError(f"ALPACA_DATA_FEED must be one of: {choices}")
    return value


def _alpaca_options_feed() -> str:
    value = os.getenv("ALPACA_OPTIONS_FEED", "indicative").strip().lower()
    if value not in {"indicative", "opra"}:
        raise ValueError("ALPACA_OPTIONS_FEED must be either indicative or opra")
    return value


def _alpaca_options_execution_adapter() -> str:
    value = os.getenv("ALPACA_OPTIONS_EXECUTION_ADAPTER", "cli").strip().lower()
    if value != "cli":
        raise ValueError(
            "ALPACA_OPTIONS_EXECUTION_ADAPTER must be cli for hackathon-compliant option execution"
        )
    return value


@dataclass(frozen=True)
class Settings:
    app_env: str
    api_auth_token: str | None
    api_auth_role: str
    api_auth_user_id: str
    api_auth_portfolio_id: str
    database_url: str
    redis_url: str | None
    redis_required: bool
    cache_ttl_seconds: int
    workflow_lock_ttl_seconds: int
    workflow_lock_wait_seconds: float
    run_migrations_on_startup: bool
    web_origin: str
    alpaca_api_key: str | None
    alpaca_secret_key: str | None
    alpaca_paper: bool
    alpaca_trading_api_url: str
    alpaca_data_feed: str
    alpaca_options_feed: str
    alpaca_options_execution_adapter: str
    alpaca_cli_path: str
    openai_api_key: str | None
    openai_model: str
    live_trading_enabled: bool
    auto_execute_paper: bool
    max_single_position_pct: float
    max_new_position_pct: float
    max_daily_loss_pct: float
    max_portfolio_drawdown_pct: float
    min_consensus_confidence: float
    min_agreeing_agents: int
    max_trades_per_day: int
    max_data_age_seconds: int
    max_volatility_annualized: float
    hedge_min_risk_score: float
    hedge_release_risk_score: float
    hedge_target_dte: int
    hedge_min_dte: int
    hedge_max_dte: int
    hedge_target_otm_pct: float
    hedge_max_otm_pct: float
    hedge_max_ratio: float
    hedge_max_premium_pct: float
    hedge_max_spread_pct: float
    hedge_max_contracts: int

    @property
    def alpaca_configured(self) -> bool:
        return bool(self.alpaca_api_key and self.alpaca_secret_key)

    @property
    def alpaca_trading_base_url(self) -> str:
        """Host root required by alpaca-py's `url_override` argument."""
        return self.alpaca_trading_api_url.removesuffix("/v2")


@lru_cache
def get_settings() -> Settings:
    return Settings(
        app_env=os.getenv("APP_ENV", "development"),
        api_auth_token=os.getenv("API_AUTH_TOKEN", "").strip() or None,
        api_auth_role=os.getenv("API_AUTH_ROLE", "operator").strip().lower(),
        api_auth_user_id=os.getenv(
            "API_AUTH_USER_ID", "00000000-0000-0000-0000-000000000001"
        ).strip(),
        api_auth_portfolio_id=os.getenv(
            "API_AUTH_PORTFOLIO_ID", "00000000-0000-0000-0000-000000000002"
        ).strip(),
        database_url=_database_url(),
        redis_url=os.getenv("REDIS_URL") or None,
        redis_required=_bool("REDIS_REQUIRED", False),
        cache_ttl_seconds=_int("CACHE_TTL_SECONDS", 30),
        workflow_lock_ttl_seconds=_int("WORKFLOW_LOCK_TTL_SECONDS", 300),
        workflow_lock_wait_seconds=_float("WORKFLOW_LOCK_WAIT_SECONDS", 0.0),
        run_migrations_on_startup=_bool("RUN_MIGRATIONS_ON_STARTUP", True),
        web_origin=os.getenv("WEB_ORIGIN", "http://localhost:3000"),
        alpaca_api_key=os.getenv("ALPACA_API_KEY") or None,
        alpaca_secret_key=os.getenv("ALPACA_SECRET_KEY") or None,
        alpaca_paper=_bool("ALPACA_PAPER", True),
        alpaca_trading_api_url=_alpaca_trading_api_url(),
        alpaca_data_feed=_alpaca_data_feed(),
        alpaca_options_feed=_alpaca_options_feed(),
        alpaca_options_execution_adapter=_alpaca_options_execution_adapter(),
        alpaca_cli_path=os.getenv("ALPACA_CLI_PATH", "alpaca").strip() or "alpaca",
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-5.6"),
        live_trading_enabled=_bool("LIVE_TRADING_ENABLED", False),
        auto_execute_paper=_bool("AUTO_EXECUTE_PAPER", False),
        max_single_position_pct=_float("MAX_SINGLE_POSITION_PCT", 0.10),
        max_new_position_pct=_float("MAX_NEW_POSITION_PCT", 0.05),
        max_daily_loss_pct=_float("MAX_DAILY_LOSS_PCT", 0.03),
        max_portfolio_drawdown_pct=_float("MAX_PORTFOLIO_DRAWDOWN_PCT", 0.08),
        min_consensus_confidence=_float("MIN_CONSENSUS_CONFIDENCE", 0.70),
        min_agreeing_agents=_int("MIN_AGREEING_AGENTS", 3),
        max_trades_per_day=_int("MAX_TRADES_PER_DAY", 10),
        max_data_age_seconds=_int("MAX_DATA_AGE_SECONDS", 120),
        max_volatility_annualized=_float("MAX_VOLATILITY_ANNUALIZED", 0.80),
        hedge_min_risk_score=_float("HEDGE_MIN_RISK_SCORE", 0.55),
        hedge_release_risk_score=_float("HEDGE_RELEASE_RISK_SCORE", 0.35),
        hedge_target_dte=_int("HEDGE_TARGET_DTE", 30),
        hedge_min_dte=_int("HEDGE_MIN_DTE", 21),
        hedge_max_dte=_int("HEDGE_MAX_DTE", 45),
        hedge_target_otm_pct=_float("HEDGE_TARGET_OTM_PCT", 0.05),
        hedge_max_otm_pct=_float("HEDGE_MAX_OTM_PCT", 0.10),
        hedge_max_ratio=_float("HEDGE_MAX_RATIO", 1.0),
        hedge_max_premium_pct=_float("HEDGE_MAX_PREMIUM_PCT", 0.02),
        hedge_max_spread_pct=_float("HEDGE_MAX_SPREAD_PCT", 0.25),
        hedge_max_contracts=_int("HEDGE_MAX_CONTRACTS", 10),
    )
