from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Action = Literal["BUY", "SELL", "HOLD"]
RiskDecision = Literal["APPROVE", "MODIFY", "REJECT", "ESCALATE"]
Severity = Literal["INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
Strategy = Literal["EQUITY", "PROTECTIVE_PUT"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceItem(StrictModel):
    label: str
    value: str
    source: str
    importance: float = Field(ge=0, le=1)


class AgentDecision(StrictModel):
    agent_name: Literal["market", "news", "quant", "portfolio"]
    display_name: str
    symbol: str
    action: Action
    confidence: float = Field(ge=0, le=1)
    thesis: str
    evidence: list[EvidenceItem]
    bullish_factors: list[str]
    bearish_factors: list[str]
    risk_flags: list[str]
    suggested_position_pct: float = Field(ge=0, le=1)
    suggested_stop_loss_pct: float | None = Field(default=None, ge=0, le=1)
    suggested_take_profit_pct: float | None = Field(default=None, ge=0, le=1)
    invalidation_conditions: list[str]
    data_timestamp: datetime
    engine: str = "rules-v1"
    latency_ms: int = 0


class RiskAgentReview(StrictModel):
    verdict: Literal["SUPPORT", "CAUTION", "REJECT_RECOMMENDATION"]
    semantic_risk_score: float = Field(ge=0, le=1)
    issues: list[str]
    explanation: str
    engine: str = "rules-v1"


class ConsensusDecision(StrictModel):
    direction: Action
    confidence: float = Field(ge=0, le=1)
    weighted_score: float = Field(ge=-1, le=1)
    agreement_ratio: float = Field(ge=0, le=1)
    disagreement_score: float = Field(ge=0, le=1)
    agreeing_agents: int
    total_agents: int
    supporting_agents: list[str]
    dissenting_agents: list[str]


class TradeProposal(StrictModel):
    workflow_run_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    consensus_confidence: float = Field(ge=0, le=1)
    requested_position_pct: float = Field(ge=0, le=1)
    requested_notional: float | None = Field(default=None, ge=0)
    stop_loss_pct: float | None = Field(default=None, ge=0, le=1)
    take_profit_pct: float | None = Field(default=None, ge=0, le=1)
    supporting_agents: list[str]
    dissenting_agents: list[str]
    thesis: str
    invalidation_conditions: list[str]
    instrument_type: Literal["EQUITY", "OPTION"] = "EQUITY"
    underlying_symbol: str | None = None
    position_intent: Literal["BUY_TO_OPEN", "SELL_TO_CLOSE"] | None = None
    hedge_plan: HedgePlan | None = None


class OptionContractSnapshot(StrictModel):
    symbol: str
    underlying_symbol: str
    option_type: Literal["PUT", "CALL"]
    expiration_date: date
    strike_price: float = Field(gt=0)
    multiplier: int = Field(default=100, gt=0)
    tradable: bool = True
    open_interest: int | None = Field(default=None, ge=0)
    bid_price: float = Field(ge=0)
    ask_price: float = Field(gt=0)
    mid_price: float = Field(gt=0)
    quote_as_of: datetime
    source: Literal["DEMO_REPLAY", "ALPACA_PAPER"]


class HedgeRiskAssessment(StrictModel):
    score: float = Field(ge=0, le=1)
    level: Literal["LOW", "ELEVATED", "HIGH", "CRITICAL"]
    components: dict[str, float]
    reasons: list[str]


class HedgePlan(StrictModel):
    action: Literal["OPEN", "HOLD", "RELEASE"]
    strategy: Literal["PROTECTIVE_PUT"] = "PROTECTIVE_PUT"
    underlying_symbol: str
    underlying_quantity: float = Field(ge=0)
    underlying_market_value: float = Field(ge=0)
    risk: HedgeRiskAssessment
    target_hedge_ratio: float = Field(ge=0, le=1)
    actual_hedge_ratio: float = Field(ge=0, le=1)
    contract: OptionContractSnapshot | None = None
    contracts: int = Field(default=0, ge=0)
    covered_shares: float = Field(default=0, ge=0)
    limit_price: float | None = Field(default=None, gt=0)
    estimated_premium: float = Field(default=0, ge=0)
    premium_pct_equity: float = Field(default=0, ge=0, le=1)
    rationale: list[str]
    release_conditions: list[str]
    rebalance_conditions: list[str]
    execution_interface: Literal["SIMULATED_REPLAY", "ALPACA_CLI"]


TradeProposal.model_rebuild()


class RiskCheckResult(StrictModel):
    rule_id: str
    rule_name: str
    passed: bool
    severity: Severity
    message: str


class RiskGateResult(StrictModel):
    decision: RiskDecision
    requested_position_pct: float = Field(ge=0, le=1)
    approved_position_pct: float = Field(ge=0, le=1)
    checks: list[RiskCheckResult]
    reasons: list[str]


class Bar(StrictModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class Indicators(StrictModel):
    sma20: float
    sma50: float
    ema12: float
    rsi14: float
    macd: float
    macd_signal: float
    atr14: float
    daily_return: float
    return_5d: float
    return_20d: float
    volatility_annualized: float
    volume_zscore: float
    support: float
    resistance: float


class MarketSnapshot(StrictModel):
    symbol: str
    price: float
    change_pct: float
    as_of: datetime
    source: Literal["DEMO_REPLAY", "ALPACA_PAPER"]
    bars: list[Bar]
    indicators: Indicators


class NewsItem(StrictModel):
    id: str
    headline: str
    summary: str
    source: str
    published_at: datetime
    sentiment: float = Field(ge=-1, le=1)
    relevance: float = Field(ge=0, le=1)
    corroborated: bool
    duplicate_group: str | None = None
    information_risk: list[str] = Field(default_factory=list)


class Position(StrictModel):
    symbol: str
    quantity: float
    market_value: float
    avg_entry_price: float
    current_price: float
    unrealized_pl: float
    unrealized_pl_pct: float
    weight: float


class AccountSnapshot(StrictModel):
    account_id: str
    status: str
    currency: str = "USD"
    equity: float
    cash: float
    buying_power: float
    options_buying_power: float | None = Field(default=None, ge=0)
    options_approved_level: int = Field(default=0, ge=0)
    options_trading_level: int = Field(default=0, ge=0)
    day_pl: float
    day_pl_pct: float
    portfolio_drawdown_pct: float
    trades_today: int
    positions: list[Position]
    open_orders: list[dict[str, Any]] = Field(default_factory=list)
    source: Literal["DEMO_REPLAY", "ALPACA_PAPER"]


class MarketClock(StrictModel):
    is_open: bool
    timestamp: datetime
    next_open: datetime
    next_close: datetime
    source: Literal["DEMO_REPLAY", "ALPACA_PAPER"]


class TimelineEvent(StrictModel):
    id: str
    event: str
    title: str
    detail: str
    status: Literal["COMPLETE", "WARNING", "BLOCKED", "PENDING"] = "COMPLETE"
    timestamp: datetime


class SocAlert(StrictModel):
    id: str
    rule_id: str
    alert_type: str
    severity: Severity
    title: str
    detail: str
    symbol: str | None = None
    workflow_run_id: str | None = None
    status: Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"] = "OPEN"
    created_at: datetime


class ExecutionOrder(StrictModel):
    id: str
    provider_order_id: str
    client_order_id: str
    workflow_run_id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    notional: float
    quantity: float | None = None
    status: str
    execution_mode: Literal["SIMULATED_PAPER", "ALPACA_PAPER"]
    submitted_at: datetime
    filled_at: datetime | None = None
    risk_decision: RiskDecision
    instrument_type: Literal["EQUITY", "OPTION"] = "EQUITY"
    underlying_symbol: str | None = None
    order_type: Literal["market", "limit"] = "market"
    limit_price: float | None = Field(default=None, gt=0)
    position_intent: Literal["BUY_TO_OPEN", "SELL_TO_CLOSE"] | None = None
    execution_interface: Literal["ALPACA_SDK", "ALPACA_CLI", "SIMULATED_REPLAY"] = (
        "ALPACA_SDK"
    )


class DecisionExplanation(StrictModel):
    headline: str
    summary: str
    final_action: Action
    confidence: float
    positive_factors: list[str]
    negative_factors: list[str]
    agent_votes: list[dict[str, Any]]
    consensus_explanation: str
    risk_decision: RiskDecision
    triggered_rules: list[dict[str, Any]]
    requested_size: float
    approved_size: float
    invalidation_conditions: list[str]
    execution_status: str | None


class WorkflowResult(StrictModel):
    workflow_run_id: str
    symbol: str
    status: Literal[
        "RUNNING", "AWAITING_APPROVAL", "COMPLETED", "REJECTED", "ESCALATED", "FAILED"
    ]
    mode: Literal["REPLAY", "LIVE"]
    scenario: str
    agent_provider: Literal["RULES", "OPENAI"]
    strategy: Strategy = "EQUITY"
    replay_of: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    market_snapshot: MarketSnapshot
    news_items: list[NewsItem]
    account: AccountSnapshot
    agent_decisions: list[AgentDecision]
    consensus: ConsensusDecision
    risk_review: RiskAgentReview
    proposal: TradeProposal | None
    hedge_plan: HedgePlan | None = None
    risk_gate: RiskGateResult
    execution: ExecutionOrder | None = None
    explanation: DecisionExplanation
    soc_alerts: list[SocAlert]
    timeline: list[TimelineEvent]
    errors: list[str] = Field(default_factory=list)


class AnalysisRequest(StrictModel):
    symbol: str = Field(min_length=1, max_length=8)
    mode: Literal["REPLAY", "LIVE"] = "REPLAY"
    scenario: Literal[
        "risk_modification", "information_risk", "agent_soc", "portfolio_protection"
    ] = "risk_modification"
    agent_provider: Literal["RULES", "OPENAI"] = "RULES"
    strategy: Strategy = "EQUITY"
    auto_execute: bool = False

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized.replace(".", "").isalpha():
            raise ValueError("symbol must contain only letters and an optional dot")
        return normalized


class AnalysisStarted(StrictModel):
    workflow_run_id: str
    status: str
    result: WorkflowResult


class RiskPolicy(StrictModel):
    key: str
    label: str
    value: float | int | bool
    unit: Literal["percent", "count", "seconds", "boolean"]
    locked: bool = False
    description: str


class RiskPolicyUpdate(StrictModel):
    value: float | int | bool


class AlertUpdate(StrictModel):
    status: Literal["OPEN", "ACKNOWLEDGED", "RESOLVED"]
