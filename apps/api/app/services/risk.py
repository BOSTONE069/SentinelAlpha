from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock

from ..config import Settings
from ..db import Repository
from ..schemas import (
    AccountSnapshot,
    ConsensusDecision,
    MarketClock,
    MarketSnapshot,
    RiskAgentReview,
    RiskCheckResult,
    RiskGateResult,
    RiskPolicy,
    TradeProposal,
)


class RiskControlState:
    def __init__(self, settings: Settings):
        self._lock = Lock()
        self.kill_switch = False
        self.values: dict[str, float | int | bool] = {
            "max_single_position_pct": settings.max_single_position_pct,
            "max_new_position_pct": settings.max_new_position_pct,
            "max_daily_loss_pct": settings.max_daily_loss_pct,
            "max_portfolio_drawdown_pct": settings.max_portfolio_drawdown_pct,
            "min_consensus_confidence": settings.min_consensus_confidence,
            "min_agreeing_agents": settings.min_agreeing_agents,
            "max_trades_per_day": settings.max_trades_per_day,
            "max_data_age_seconds": settings.max_data_age_seconds,
            "max_volatility_annualized": settings.max_volatility_annualized,
            "hedge_min_risk_score": settings.hedge_min_risk_score,
            "hedge_release_risk_score": settings.hedge_release_risk_score,
            "hedge_target_dte": settings.hedge_target_dte,
            "hedge_min_dte": settings.hedge_min_dte,
            "hedge_max_dte": settings.hedge_max_dte,
            "hedge_target_otm_pct": settings.hedge_target_otm_pct,
            "hedge_max_otm_pct": settings.hedge_max_otm_pct,
            "hedge_max_ratio": settings.hedge_max_ratio,
            "hedge_max_premium_pct": settings.hedge_max_premium_pct,
            "hedge_max_spread_pct": settings.hedge_max_spread_pct,
            "hedge_max_contracts": settings.hedge_max_contracts,
            "allow_shorting": False,
            "allow_extended_hours": False,
            "paper_mode": True,
        }

    def update(self, key: str, value: float | int | bool) -> None:
        if key in {"paper_mode"}:
            raise ValueError(f"{key} is locked")
        if key not in self.values:
            raise KeyError(key)
        percent_keys = {
            "max_single_position_pct",
            "max_new_position_pct",
            "max_daily_loss_pct",
            "max_portfolio_drawdown_pct",
            "min_consensus_confidence",
            "max_volatility_annualized",
            "hedge_min_risk_score",
            "hedge_release_risk_score",
            "hedge_target_otm_pct",
            "hedge_max_otm_pct",
            "hedge_max_ratio",
            "hedge_max_premium_pct",
            "hedge_max_spread_pct",
        }
        boolean_keys = {"allow_shorting", "allow_extended_hours"}
        if key in percent_keys and (isinstance(value, bool) or not 0 <= float(value) <= 1):
            raise ValueError(f"{key} must be between 0 and 1")
        if key in boolean_keys and not isinstance(value, bool):
            raise ValueError(f"{key} must be a boolean")
        if key in {
            "min_agreeing_agents",
            "max_trades_per_day",
            "hedge_target_dte",
            "hedge_min_dte",
            "hedge_max_dte",
            "hedge_max_contracts",
        } and (
            isinstance(value, bool) or int(value) != value or not 1 <= int(value) <= 100
        ):
            raise ValueError(f"{key} must be a whole number between 1 and 100")
        if key == "max_data_age_seconds" and (
            isinstance(value, bool) or int(value) != value or not 1 <= int(value) <= 86_400
        ):
            raise ValueError("max_data_age_seconds must be between 1 and 86400")
        with self._lock:
            prospective = {**self.values, key: value}
            if not (
                int(prospective["hedge_min_dte"])
                <= int(prospective["hedge_target_dte"])
                <= int(prospective["hedge_max_dte"])
            ):
                raise ValueError(
                    "hedge DTE controls must satisfy minimum <= target <= maximum"
                )
            if float(prospective["hedge_release_risk_score"]) >= float(
                prospective["hedge_min_risk_score"]
            ):
                raise ValueError(
                    "hedge release score must be below the minimum hedge score"
                )
            if float(prospective["hedge_target_otm_pct"]) > float(
                prospective["hedge_max_otm_pct"]
            ):
                raise ValueError(
                    "target hedge OTM percentage cannot exceed the maximum"
                )
            self.values[key] = value

    def policies(self) -> list[RiskPolicy]:
        definitions = {
            "max_single_position_pct": ("Maximum single position", "percent", "Hard cap for total symbol exposure."),
            "max_new_position_pct": ("Maximum new position", "percent", "Maximum exposure added by one workflow."),
            "max_daily_loss_pct": ("Daily loss limit", "percent", "Blocks new risk after this daily loss."),
            "max_portfolio_drawdown_pct": ("Portfolio drawdown limit", "percent", "Activates the execution kill switch."),
            "min_consensus_confidence": ("Minimum consensus", "percent", "Required code-derived council confidence."),
            "min_agreeing_agents": ("Minimum agreeing agents", "count", "Minimum matching analytical votes."),
            "max_trades_per_day": ("Trades per day", "count", "Daily execution ceiling."),
            "max_data_age_seconds": ("Maximum data age", "seconds", "Rejects market inputs older than this."),
            "max_volatility_annualized": ("Maximum volatility", "percent", "Annualized volatility ceiling."),
            "hedge_min_risk_score": ("Minimum hedge risk", "percent", "Risk score required before opening protection."),
            "hedge_release_risk_score": ("Hedge release risk", "percent", "Risk score below which an existing hedge may be released."),
            "hedge_target_dte": ("Target option DTE", "count", "Preferred days to expiration for protective puts."),
            "hedge_min_dte": ("Minimum option DTE", "count", "Rejects contracts too close to expiration."),
            "hedge_max_dte": ("Maximum option DTE", "count", "Rejects contracts beyond the hedge horizon."),
            "hedge_target_otm_pct": ("Target put OTM", "percent", "Preferred protective-put strike below spot."),
            "hedge_max_otm_pct": ("Maximum put OTM", "percent", "Rejects protection with an excessively distant strike."),
            "hedge_max_ratio": ("Maximum hedge ratio", "percent", "Caps protected underlying shares relative to the position."),
            "hedge_max_premium_pct": ("Maximum premium budget", "percent", "Caps option premium as a share of account equity."),
            "hedge_max_spread_pct": ("Maximum option spread", "percent", "Rejects illiquid option quotes by bid/ask spread."),
            "hedge_max_contracts": ("Maximum hedge contracts", "count", "Caps contracts opened by one hedge workflow."),
            "allow_shorting": ("Allow shorting", "boolean", "Short exposure is disabled for the MVP."),
            "allow_extended_hours": ("Allow extended hours", "boolean", "Regular market hours only."),
            "paper_mode": ("Paper mode", "boolean", "Execution environment is permanently locked to paper."),
        }
        return [
            RiskPolicy(
                key=key,
                label=definitions[key][0],
                value=value,
                unit=definitions[key][1],
                locked=key == "paper_mode",
                description=definitions[key][2],
            )
            for key, value in self.values.items()
        ]


def _check(rule: str, name: str, passed: bool, severity: str, message: str) -> RiskCheckResult:
    return RiskCheckResult(rule_id=rule, rule_name=name, passed=passed, severity=severity, message=message)


class RiskEngine:
    def __init__(self, settings: Settings, controls: RiskControlState, repository: Repository):
        self.settings = settings
        self.controls = controls
        self.repository = repository

    def evaluate(
        self,
        proposal: TradeProposal,
        consensus: ConsensusDecision,
        review: RiskAgentReview,
        market: MarketSnapshot,
        account: AccountSnapshot,
        clock: MarketClock,
    ) -> RiskGateResult:
        policy = self.controls.values
        checks: list[RiskCheckResult] = []
        hard_reject = False

        paper_pass = self.settings.alpaca_paper and not self.settings.live_trading_enabled
        checks.append(_check("R001", "Paper mode", paper_pass, "CRITICAL", "Paper-only execution boundary is locked." if paper_pass else "Paper-only boundary is not configured."))
        hard_reject |= not paper_pass

        confidence_pass = consensus.confidence >= float(policy["min_consensus_confidence"])
        checks.append(_check("R002", "Minimum confidence", confidence_pass, "HIGH", f"Consensus {consensus.confidence:.0%}; minimum {float(policy['min_consensus_confidence']):.0%}."))
        hard_reject |= not confidence_pass

        agreement_pass = consensus.agreeing_agents >= int(policy["min_agreeing_agents"])
        checks.append(_check("R003", "Agent agreement", agreement_pass, "HIGH", f"{consensus.agreeing_agents}/{consensus.total_agents} agents agree; minimum {int(policy['min_agreeing_agents'])}."))
        hard_reject |= not agreement_pass

        current_weight = next((p.weight for p in account.positions if p.symbol == proposal.symbol), 0.0)
        remaining_capacity = max(0.0, float(policy["max_single_position_pct"]) - current_weight)
        approved_pct = min(proposal.requested_position_pct, float(policy["max_new_position_pct"]), remaining_capacity)
        size_pass = approved_pct >= proposal.requested_position_pct - 1e-9
        checks.append(_check("R004", "Position limit", size_pass, "HIGH" if not size_pass else "INFO", f"Requested {proposal.requested_position_pct:.1%}; current exposure {current_weight:.1%}; permissible addition {approved_pct:.1%}."))
        if approved_pct <= 0:
            hard_reject = True

        notional = account.equity * approved_pct
        buying_power_pass = notional <= account.buying_power and account.buying_power > 0
        checks.append(_check("R005", "Buying power", buying_power_pass, "CRITICAL", f"Approved notional ${notional:,.0f}; buying power ${account.buying_power:,.0f}."))
        if not buying_power_pass:
            approved_pct = min(approved_pct, max(0, account.buying_power / account.equity))
            hard_reject |= approved_pct <= 0

        age_seconds = max(0, (datetime.now(timezone.utc) - market.as_of).total_seconds())
        freshness_pass = age_seconds <= int(policy["max_data_age_seconds"])
        checks.append(_check("R006", "Data freshness", freshness_pass, "CRITICAL", f"Market input age {age_seconds:.0f}s; maximum {int(policy['max_data_age_seconds'])}s."))
        hard_reject |= not freshness_pass

        duplicate = self.repository.has_active_intent(proposal.symbol, proposal.side, proposal.workflow_run_id)
        checks.append(_check("R007", "Duplicate order", not duplicate, "CRITICAL", "No active duplicate intent found." if not duplicate else "A matching active order already exists."))
        hard_reject |= duplicate

        trades = max(account.trades_today, self.repository.trades_today())
        trades_pass = trades < int(policy["max_trades_per_day"])
        checks.append(_check("R008", "Daily trade limit", trades_pass, "HIGH", f"{trades}/{int(policy['max_trades_per_day'])} daily executions used."))
        hard_reject |= not trades_pass

        loss_pass = account.day_pl_pct > -float(policy["max_daily_loss_pct"])
        checks.append(_check("R009", "Daily loss", loss_pass, "CRITICAL", f"Day P/L {account.day_pl_pct:+.2%}; loss limit {-float(policy['max_daily_loss_pct']):.2%}."))
        hard_reject |= not loss_pass

        drawdown_pass = account.portfolio_drawdown_pct < float(policy["max_portfolio_drawdown_pct"]) and not self.controls.kill_switch
        checks.append(_check("R010", "Drawdown / kill switch", drawdown_pass, "CRITICAL", f"Drawdown {account.portfolio_drawdown_pct:.2%}; kill switch {'ON' if self.controls.kill_switch else 'OFF'}."))
        hard_reject |= not drawdown_pass

        market_pass = clock.is_open or bool(policy["allow_extended_hours"])
        checks.append(_check("R011", "Market-hours policy", market_pass, "HIGH", "Regular session is open." if clock.is_open else "Market is closed and extended hours are disabled."))
        hard_reject |= not market_pass

        semantic_pass = review.verdict != "REJECT_RECOMMENDATION"
        checks.append(_check("R012", "Semantic risk review", semantic_pass, "HIGH", f"Risk agent verdict: {review.verdict}. {review.explanation}"))

        volatility_pass = market.indicators.volatility_annualized <= float(policy["max_volatility_annualized"])
        checks.append(_check("R013", "Volatility ceiling", volatility_pass, "HIGH", f"Annualized volatility {market.indicators.volatility_annualized:.1%}; maximum {float(policy['max_volatility_annualized']):.1%}."))
        hard_reject |= not volatility_pass

        shorting_pass = not (
            proposal.side == "SELL" and current_weight <= 0 and not bool(policy["allow_shorting"])
        )
        checks.append(_check("R014", "Shorting policy", shorting_pass, "CRITICAL", "Order does not create prohibited short exposure." if shorting_pass else "SELL would create short exposure while shorting is disabled."))
        hard_reject |= not shorting_pass

        reasons: list[str] = []
        if hard_reject:
            decision = "REJECT"
            approved_pct = 0
            reasons = [check.message for check in checks if not check.passed and check.rule_id != "R012"]
        elif not semantic_pass:
            decision = "ESCALATE"
            approved_pct = 0
            reasons = ["Qualitative risk review requires human escalation before any execution."]
        elif not size_pass or not buying_power_pass:
            decision = "MODIFY"
            reasons = [f"Position reduced from {proposal.requested_position_pct:.1%} to {approved_pct:.1%} by deterministic limits."]
        else:
            decision = "APPROVE"
            reasons = ["All deterministic execution constraints passed."]

        return RiskGateResult(
            decision=decision,
            requested_position_pct=proposal.requested_position_pct,
            approved_position_pct=round(approved_pct, 6),
            checks=checks,
            reasons=reasons,
        )
