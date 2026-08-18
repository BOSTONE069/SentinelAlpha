from __future__ import annotations

import math
from datetime import datetime, timezone

from ..config import Settings
from ..db import Repository
from ..schemas import (
    AccountSnapshot,
    AgentDecision,
    ConsensusDecision,
    HedgePlan,
    HedgeRiskAssessment,
    MarketClock,
    MarketSnapshot,
    NewsItem,
    OptionContractSnapshot,
    RiskAgentReview,
    RiskCheckResult,
    RiskGateResult,
    TradeProposal,
)
from .risk import RiskControlState


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def assess_hedge_risk(
    market: MarketSnapshot,
    news: list[NewsItem],
    account: AccountSnapshot,
    decisions: list[AgentDecision],
    controls: RiskControlState,
) -> HedgeRiskAssessment:
    position = next(
        (item for item in account.positions if item.symbol == market.symbol), None
    )
    weight = position.weight if position else 0.0
    weighted_sentiment = sum(item.sentiment * item.relevance for item in news) / max(
        sum(item.relevance for item in news), 1.0
    )
    sell_votes = sum(item.action == "SELL" for item in decisions)
    components = {
        "concentration": _clamp(weight / 0.20),
        "volatility": _clamp(market.indicators.volatility_annualized / 0.55),
        "negative_momentum": _clamp(-market.indicators.return_20d / 0.12),
        "negative_news": _clamp(-weighted_sentiment),
        "drawdown": _clamp(
            account.portfolio_drawdown_pct
            / max(float(controls.values["max_portfolio_drawdown_pct"]), 0.001)
        ),
        "council_defensiveness": sell_votes / max(len(decisions), 1),
    }
    score = round(
        0.25 * components["concentration"]
        + 0.20 * components["volatility"]
        + 0.20 * components["negative_momentum"]
        + 0.15 * components["negative_news"]
        + 0.10 * components["drawdown"]
        + 0.10 * components["council_defensiveness"],
        4,
    )
    if score >= 0.85:
        level = "CRITICAL"
    elif score >= 0.70:
        level = "HIGH"
    elif score >= float(controls.values["hedge_min_risk_score"]):
        level = "ELEVATED"
    else:
        level = "LOW"

    reasons: list[str] = []
    if components["concentration"] >= 0.75:
        reasons.append(f"{market.symbol} concentration is {weight:.1%} of portfolio equity")
    if components["volatility"] >= 0.65:
        reasons.append(
            f"annualized volatility is elevated at {market.indicators.volatility_annualized:.1%}"
        )
    if components["negative_momentum"] >= 0.35:
        reasons.append(
            f"20-day return has deteriorated to {market.indicators.return_20d:+.1%}"
        )
    if components["negative_news"] >= 0.25:
        reasons.append(f"weighted news sentiment is negative at {weighted_sentiment:+.2f}")
    if components["drawdown"] >= 0.50:
        reasons.append(
            f"portfolio drawdown has reached {account.portfolio_drawdown_pct:.1%}"
        )
    if sell_votes:
        reasons.append(f"{sell_votes}/{len(decisions)} analytical agents favor defense")
    if not reasons:
        reasons.append("portfolio risk remains inside the normal operating range")

    return HedgeRiskAssessment(
        score=score,
        level=level,
        components=components,
        reasons=reasons,
    )


def _target_ratio(score: float) -> float:
    if score >= 0.85:
        return 1.0
    if score >= 0.72:
        return 0.75
    if score >= 0.62:
        return 0.50
    return 0.25


def _select_contract(
    contracts: list[OptionContractSnapshot],
    market: MarketSnapshot,
    controls: RiskControlState,
) -> OptionContractSnapshot | None:
    today = market.as_of.date()
    target_dte = int(controls.values["hedge_target_dte"])
    min_dte = int(controls.values["hedge_min_dte"])
    max_dte = int(controls.values["hedge_max_dte"])
    target_strike = market.price * (1 - float(controls.values["hedge_target_otm_pct"]))
    max_otm = float(controls.values["hedge_max_otm_pct"])

    eligible: list[OptionContractSnapshot] = []
    for contract in contracts:
        dte = (contract.expiration_date - today).days
        otm = (market.price - contract.strike_price) / market.price
        if (
            contract.option_type == "PUT"
            and contract.tradable
            and min_dte <= dte <= max_dte
            and 0 <= otm <= max_otm
            and contract.ask_price > 0
        ):
            eligible.append(contract)
    if not eligible:
        return None

    def rank(contract: OptionContractSnapshot) -> tuple[float, float, float]:
        dte = (contract.expiration_date - today).days
        spread = (contract.ask_price - contract.bid_price) / max(
            contract.mid_price, 0.01
        )
        return (
            abs(dte - target_dte),
            abs(contract.strike_price - target_strike),
            spread,
        )

    return min(eligible, key=rank)


def build_protective_put_plan(
    run_id: str,
    market: MarketSnapshot,
    news: list[NewsItem],
    account: AccountSnapshot,
    decisions: list[AgentDecision],
    contracts: list[OptionContractSnapshot],
    controls: RiskControlState,
    mode: str,
) -> HedgePlan:
    risk = assess_hedge_risk(market, news, account, decisions, controls)
    position = next(
        (item for item in account.positions if item.symbol == market.symbol), None
    )
    release_conditions = [
        f"risk score falls below {float(controls.values['hedge_release_risk_score']):.0%}",
        "negative event risk passes and news sentiment normalizes",
        "the underlying recovers above its 20-day trend with lower volatility",
        "close or roll before the option reaches seven days to expiration",
    ]
    rebalance_conditions = [
        "underlying share quantity changes by 25% or more",
        "actual hedge ratio drifts more than 20 percentage points from target",
        "a volatility regime change makes the selected contract inefficient",
    ]
    interface = "SIMULATED_REPLAY" if mode == "REPLAY" else "ALPACA_CLI"
    target_ratio = _target_ratio(risk.score)

    if position is None or position.quantity < 100:
        return HedgePlan(
            action="HOLD",
            underlying_symbol=market.symbol,
            underlying_quantity=position.quantity if position else 0,
            underlying_market_value=position.market_value if position else 0,
            risk=risk,
            target_hedge_ratio=target_ratio,
            actual_hedge_ratio=0,
            rationale=[
                "A protective put was not opened because no full 100-share contract lot is available."
            ],
            release_conditions=release_conditions,
            rebalance_conditions=rebalance_conditions,
            execution_interface=interface,
        )

    if risk.score < float(controls.values["hedge_min_risk_score"]):
        return HedgePlan(
            action="HOLD",
            underlying_symbol=market.symbol,
            underlying_quantity=position.quantity,
            underlying_market_value=position.market_value,
            risk=risk,
            target_hedge_ratio=0,
            actual_hedge_ratio=0,
            rationale=[
                "Risk is below the configured activation threshold; buying protection would add unnecessary premium drag."
            ],
            release_conditions=release_conditions,
            rebalance_conditions=rebalance_conditions,
            execution_interface=interface,
        )

    selected = _select_contract(contracts, market, controls)
    if selected is None:
        return HedgePlan(
            action="HOLD",
            underlying_symbol=market.symbol,
            underlying_quantity=position.quantity,
            underlying_market_value=position.market_value,
            risk=risk,
            target_hedge_ratio=target_ratio,
            actual_hedge_ratio=0,
            rationale=[
                "No tradable put satisfied the configured strike and expiration window."
            ],
            release_conditions=release_conditions,
            rebalance_conditions=rebalance_conditions,
            execution_interface=interface,
        )

    max_whole_contracts = math.floor(position.quantity / selected.multiplier)
    requested_contracts = math.ceil(
        position.quantity * target_ratio / selected.multiplier
    )
    contract_count = min(
        max_whole_contracts,
        requested_contracts,
        int(controls.values["hedge_max_contracts"]),
    )
    covered_shares = contract_count * selected.multiplier
    actual_ratio = covered_shares / position.quantity
    limit_price = round(selected.ask_price, 2)
    premium = round(limit_price * selected.multiplier * contract_count, 2)
    premium_pct = premium / account.equity if account.equity else 0

    return HedgePlan(
        action="OPEN",
        underlying_symbol=market.symbol,
        underlying_quantity=position.quantity,
        underlying_market_value=position.market_value,
        risk=risk,
        target_hedge_ratio=target_ratio,
        actual_hedge_ratio=actual_ratio,
        contract=selected,
        contracts=contract_count,
        covered_shares=covered_shares,
        limit_price=limit_price,
        estimated_premium=premium,
        premium_pct_equity=premium_pct,
        rationale=[
            *risk.reasons,
            f"buy {contract_count} {selected.expiration_date.isoformat()} {selected.strike_price:g} put at a ${limit_price:.2f} limit",
            f"protect {covered_shares:g} of {position.quantity:g} shares ({actual_ratio:.0%})",
        ],
        release_conditions=release_conditions,
        rebalance_conditions=rebalance_conditions,
        execution_interface=interface,
    )


def hedge_trade_proposal(
    run_id: str,
    plan: HedgePlan,
    consensus: ConsensusDecision,
) -> TradeProposal | None:
    if plan.action != "OPEN" or not plan.contract:
        return None
    return TradeProposal(
        workflow_run_id=run_id,
        symbol=plan.contract.symbol,
        side="BUY",
        consensus_confidence=consensus.confidence,
        requested_position_pct=plan.premium_pct_equity,
        requested_notional=plan.estimated_premium,
        supporting_agents=consensus.supporting_agents,
        dissenting_agents=consensus.dissenting_agents,
        thesis="; ".join(plan.rationale),
        invalidation_conditions=plan.release_conditions,
        instrument_type="OPTION",
        underlying_symbol=plan.underlying_symbol,
        position_intent="BUY_TO_OPEN",
        hedge_plan=plan,
    )


def _check(
    rule: str, name: str, passed: bool, severity: str, message: str
) -> RiskCheckResult:
    return RiskCheckResult(
        rule_id=rule,
        rule_name=name,
        passed=passed,
        severity=severity,
        message=message,
    )


class HedgeRiskEngine:
    """Fail-closed deterministic controls for protective option orders."""

    def __init__(
        self,
        settings: Settings,
        controls: RiskControlState,
        repository: Repository,
    ):
        self.settings = settings
        self.controls = controls
        self.repository = repository

    def evaluate(
        self,
        run_id: str,
        plan: HedgePlan,
        review: RiskAgentReview,
        market: MarketSnapshot,
        account: AccountSnapshot,
        clock: MarketClock,
    ) -> RiskGateResult:
        policy = self.controls.values
        checks: list[RiskCheckResult] = []

        paper_pass = self.settings.alpaca_paper and not self.settings.live_trading_enabled
        checks.append(
            _check(
                "H001",
                "Paper mode",
                paper_pass,
                "CRITICAL",
                "Alpaca paper execution is locked."
                if paper_pass
                else "Paper-only execution is not configured.",
            )
        )
        position = next(
            (item for item in account.positions if item.symbol == plan.underlying_symbol),
            None,
        )
        position_pass = position is not None and position.quantity >= 100
        checks.append(
            _check(
                "H002",
                "Protectable underlying position",
                position_pass,
                "CRITICAL",
                f"Underlying position contains {position.quantity:g} shares."
                if position
                else "No underlying position exists.",
            )
        )
        trigger_pass = plan.risk.score >= float(policy["hedge_min_risk_score"])
        checks.append(
            _check(
                "H003",
                "Hedge activation threshold",
                trigger_pass,
                "HIGH",
                f"Risk score {plan.risk.score:.0%}; activation threshold {float(policy['hedge_min_risk_score']):.0%}.",
            )
        )
        contract_pass = (
            plan.action == "OPEN"
            and plan.contract is not None
            and plan.contract.option_type == "PUT"
            and plan.contract.tradable
        )
        checks.append(
            _check(
                "H004",
                "Protective-put contract",
                contract_pass,
                "CRITICAL",
                "Selected contract is an active, tradable put."
                if contract_pass
                else "No eligible protective-put contract was selected.",
            )
        )

        dte = (
            (plan.contract.expiration_date - market.as_of.date()).days
            if plan.contract
            else 0
        )
        expiry_pass = int(policy["hedge_min_dte"]) <= dte <= int(
            policy["hedge_max_dte"]
        )
        checks.append(
            _check(
                "H005",
                "Expiration window",
                expiry_pass,
                "HIGH",
                f"Selected contract has {dte} DTE; allowed range {int(policy['hedge_min_dte'])}-{int(policy['hedge_max_dte'])}.",
            )
        )
        otm = (
            (market.price - plan.contract.strike_price) / market.price
            if plan.contract
            else 1.0
        )
        strike_pass = 0 <= otm <= float(policy["hedge_max_otm_pct"])
        checks.append(
            _check(
                "H006",
                "Strike distance",
                strike_pass,
                "HIGH",
                f"Put strike is {otm:.1%} out of the money; maximum {float(policy['hedge_max_otm_pct']):.1%}.",
            )
        )
        ratio_pass = (
            plan.contracts > 0
            and plan.actual_hedge_ratio <= float(policy["hedge_max_ratio"]) + 1e-9
            and plan.contracts <= int(policy["hedge_max_contracts"])
        )
        checks.append(
            _check(
                "H007",
                "Hedge size",
                ratio_pass,
                "CRITICAL",
                f"{plan.contracts} contract(s) protect {plan.actual_hedge_ratio:.0%} of the position; cap {float(policy['hedge_max_ratio']):.0%}.",
            )
        )
        option_buying_power = (
            account.options_buying_power
            if account.options_buying_power is not None
            else account.buying_power
        )
        premium_pass = (
            plan.estimated_premium <= option_buying_power
            and plan.premium_pct_equity <= float(policy["hedge_max_premium_pct"])
        )
        checks.append(
            _check(
                "H008",
                "Premium budget",
                premium_pass,
                "CRITICAL",
                f"Estimated premium ${plan.estimated_premium:,.2f} is {plan.premium_pct_equity:.2%} of equity; cap {float(policy['hedge_max_premium_pct']):.2%}.",
            )
        )
        spread = (
            (plan.contract.ask_price - plan.contract.bid_price)
            / max(plan.contract.mid_price, 0.01)
            if plan.contract
            else 1.0
        )
        liquidity_pass = spread <= float(policy["hedge_max_spread_pct"])
        checks.append(
            _check(
                "H009",
                "Option liquidity",
                liquidity_pass,
                "HIGH",
                f"Relative bid/ask spread {spread:.1%}; maximum {float(policy['hedge_max_spread_pct']):.1%}.",
            )
        )
        quote_age = (
            max(
                0.0,
                (
                    datetime.now(timezone.utc) - plan.contract.quote_as_of
                ).total_seconds(),
            )
            if plan.contract
            else float("inf")
        )
        freshness_pass = quote_age <= int(policy["max_data_age_seconds"])
        checks.append(
            _check(
                "H010",
                "Option quote freshness",
                freshness_pass,
                "CRITICAL",
                f"Option quote age {quote_age:.0f}s; maximum {int(policy['max_data_age_seconds'])}s.",
            )
        )
        duplicate = bool(
            plan.contract
            and self.repository.has_active_intent(
                plan.contract.symbol, "BUY", exclude_run_id=run_id
            )
        )
        checks.append(
            _check(
                "H011",
                "Duplicate hedge",
                not duplicate,
                "CRITICAL",
                "No active duplicate option intent found."
                if not duplicate
                else "A matching option order is already active.",
            )
        )
        trades = max(account.trades_today, self.repository.trades_today())
        trades_pass = trades < int(policy["max_trades_per_day"])
        checks.append(
            _check(
                "H012",
                "Daily execution count",
                trades_pass,
                "HIGH",
                f"{trades}/{int(policy['max_trades_per_day'])} daily executions used.",
            )
        )
        hours_pass = clock.is_open or bool(policy["allow_extended_hours"])
        checks.append(
            _check(
                "H013",
                "Market-hours policy",
                hours_pass,
                "HIGH",
                "Regular session is open."
                if clock.is_open
                else "Market is closed and extended hours are disabled.",
            )
        )
        semantic_pass = review.verdict != "REJECT_RECOMMENDATION"
        checks.append(
            _check(
                "H014",
                "Semantic risk review",
                semantic_pass,
                "HIGH",
                f"Risk agent verdict: {review.verdict}. {review.explanation}",
            )
        )
        switch_pass = not self.controls.kill_switch
        checks.append(
            _check(
                "H015",
                "Execution kill switch",
                switch_pass,
                "CRITICAL",
                "Kill switch is OFF."
                if switch_pass
                else "Kill switch is ON; even risk-reducing orders require review.",
            )
        )
        interface_pass = plan.execution_interface in {
            "ALPACA_CLI",
            "SIMULATED_REPLAY",
        }
        checks.append(
            _check(
                "H016",
                "Hackathon execution interface",
                interface_pass,
                "CRITICAL",
                f"Execution interface is {plan.execution_interface.replace('_', ' ')}.",
            )
        )
        permission_pass = (
            account.options_approved_level >= 2
            and account.options_trading_level >= 2
        )
        checks.append(
            _check(
                "H017",
                "Options account permission",
                permission_pass,
                "CRITICAL",
                f"Approved level {account.options_approved_level}; active trading level {account.options_trading_level}; long puts require level 2 or higher.",
            )
        )

        hard_failures = [
            check
            for check in checks
            if not check.passed and check.rule_id != "H014"
        ]
        if hard_failures:
            decision = "REJECT"
            approved_pct = 0.0
            reasons = [check.message for check in hard_failures]
        elif not semantic_pass:
            decision = "ESCALATE"
            approved_pct = 0.0
            reasons = [
                "The semantic risk review requires human investigation before protection is opened."
            ]
        else:
            decision = "APPROVE"
            approved_pct = plan.premium_pct_equity
            reasons = [
                f"Protective put approved: {plan.contracts} contract(s), {plan.actual_hedge_ratio:.0%} coverage, ${plan.estimated_premium:,.2f} maximum premium."
            ]

        return RiskGateResult(
            decision=decision,
            requested_position_pct=plan.premium_pct_equity,
            approved_position_pct=approved_pct,
            checks=checks,
            reasons=reasons,
        )
