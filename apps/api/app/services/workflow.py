from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from ..config import Settings
from ..coordination import CoordinationBackend, get_coordination
from ..db import Repository
from ..schemas import (
    AnalysisRequest,
    TimelineEvent,
    TradeProposal,
    WorkflowResult,
)
from .agents import run_agent_council
from .alpaca import AlpacaService
from .consensus import build_consensus
from .explanation import build_explanation, build_hedge_explanation
from .hedging import HedgeRiskEngine, build_protective_put_plan, hedge_trade_proposal
from .risk import RiskControlState, RiskEngine
from .soc import run_soc_checks


def _event(event: str, title: str, detail: str, status: str = "COMPLETE") -> TimelineEvent:
    return TimelineEvent(
        id=f"evt-{uuid4().hex[:10]}",
        event=event,
        title=title,
        detail=detail,
        status=status,
        timestamp=datetime.now(timezone.utc),
    )


class WorkflowService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        controls: RiskControlState,
        coordination: CoordinationBackend | None = None,
        portfolio_id: str | None = None,
    ):
        self.coordination = coordination or get_coordination()
        self.repository = Repository(db, self.coordination)
        self.settings = settings
        self.controls = controls
        self.portfolio_id = portfolio_id
        self.alpaca = AlpacaService(settings, self.coordination)

    def analyze(self, request: AnalysisRequest, replay_of: str | None = None) -> WorkflowResult:
        run_id = str(uuid4())
        lock_name = f"analysis:{request.mode.lower()}:{request.symbol}"
        with self.coordination.lock(lock_name):
            self.repository.create_workflow_run(
                run_id,
                symbol=request.symbol,
                mode=request.mode,
                scenario=request.scenario,
                agent_provider=request.agent_provider,
                strategy=request.strategy,
                replay_of=replay_of,
                portfolio_id=self.portfolio_id,
            )
            try:
                return self._analyze_locked(request, run_id, replay_of)
            except Exception as exc:
                self.repository.fail_workflow(run_id, exc)
                raise

    def _analyze_locked(
        self,
        request: AnalysisRequest,
        run_id: str,
        replay_of: str | None,
    ) -> WorkflowResult:
        started = datetime.now(timezone.utc)
        timeline = [
            _event(
                "workflow.started",
                "Agent Council started",
                f"{request.symbol} entered the supervised {request.mode.lower()} pipeline.",
            )
        ]
        errors: list[str] = []

        market = self.alpaca.market(request.symbol, request.mode, request.scenario)
        timeline.append(_event("market.loaded", "Market context loaded", f"{len(market.bars)} bars and {len(type(market.indicators).model_fields)} indicators loaded from {market.source}."))
        news = self.alpaca.news(request.symbol, request.mode, request.scenario)
        timeline.append(_event("news.loaded", "News context isolated", f"{len(news)} untrusted news items normalized and scanned."))
        account = self.alpaca.account(request.mode, request.symbol, request.scenario)
        clock = self.alpaca.clock(request.mode)
        timeline.append(_event("portfolio.loaded", "Paper portfolio loaded", f"Equity ${account.equity:,.0f}; buying power ${account.buying_power:,.0f}."))

        def on_fallback(message: str) -> None:
            errors.append(message)
            timeline.append(_event("agent.fallback", "Agent provider fallback", message, "WARNING"))

        decisions, risk_review = run_agent_council(
            self.settings,
            request.agent_provider,
            request.scenario,
            market,
            news,
            account,
            on_fallback,
        )
        actual_provider = "OPENAI" if all(d.engine.startswith("openai:") for d in decisions) else "RULES"
        for decision in decisions:
            timeline.append(
                _event(
                    f"{decision.agent_name}_agent.completed",
                    f"{decision.display_name} voted {decision.action}",
                    f"Confidence {decision.confidence:.0%} · {decision.thesis}",
                )
            )

        consensus = build_consensus(decisions)
        timeline.append(
            _event(
                "consensus.completed",
                f"Consensus resolved to {consensus.direction}",
                f"Weighted score {consensus.weighted_score:+.3f}; agreement {consensus.agreeing_agents}/{consensus.total_agents}.",
            )
        )
        timeline.append(
            _event(
                "risk.reviewed",
                f"Semantic review: {risk_review.verdict}",
                risk_review.explanation,
                "WARNING" if risk_review.verdict != "SUPPORT" else "COMPLETE",
            )
        )

        proposal = None
        hedge_plan = None
        if request.strategy == "PROTECTIVE_PUT":
            option_contracts = self.alpaca.option_contracts(
                request.symbol, market.price, request.mode
            )
            timeline.append(
                _event(
                    "options.loaded",
                    "Protective-put universe loaded",
                    f"{len(option_contracts)} put contracts normalized from "
                    f"{'the deterministic replay chain' if request.mode == 'REPLAY' else 'Alpaca option data'}.",
                )
            )
            hedge_plan = build_protective_put_plan(
                run_id,
                market,
                news,
                account,
                decisions,
                option_contracts,
                self.controls,
                request.mode,
            )
            timeline.append(
                _event(
                    "hedge_agent.completed",
                    f"Hedge Agent returned {hedge_plan.action}",
                    hedge_plan.rationale[-1],
                    "WARNING" if hedge_plan.action == "HOLD" else "COMPLETE",
                )
            )
            proposal = hedge_trade_proposal(run_id, hedge_plan, consensus)
            gate = HedgeRiskEngine(
                self.settings, self.controls, self.repository
            ).evaluate(
                run_id,
                hedge_plan,
                risk_review,
                market,
                account,
                clock,
            )
        elif consensus.direction in {"BUY", "SELL"}:
            portfolio = next(decision for decision in decisions if decision.agent_name == "portfolio")
            proposal = TradeProposal(
                workflow_run_id=run_id,
                symbol=request.symbol,
                side=consensus.direction,
                consensus_confidence=consensus.confidence,
                requested_position_pct=portfolio.suggested_position_pct,
                requested_notional=round(account.equity * portfolio.suggested_position_pct, 2),
                stop_loss_pct=portfolio.suggested_stop_loss_pct,
                take_profit_pct=portfolio.suggested_take_profit_pct,
                supporting_agents=consensus.supporting_agents,
                dissenting_agents=consensus.dissenting_agents,
                thesis=" ".join(decision.thesis for decision in decisions if decision.action == consensus.direction),
                invalidation_conditions=list(
                    dict.fromkeys(
                        condition for decision in decisions for condition in decision.invalidation_conditions
                    )
                ),
            )

        if request.strategy == "EQUITY" and proposal:
            gate = RiskEngine(self.settings, self.controls, self.repository).evaluate(
                proposal, consensus, risk_review, market, account, clock
            )
        elif request.strategy == "EQUITY":
            from ..schemas import RiskCheckResult, RiskGateResult

            gate = RiskGateResult(
                decision="REJECT",
                requested_position_pct=0,
                approved_position_pct=0,
                checks=[
                    RiskCheckResult(
                        rule_id="R000",
                        rule_name="Actionable consensus",
                        passed=False,
                        severity="INFO",
                        message="HOLD consensus creates no executable proposal.",
                    )
                ],
                reasons=["The council returned HOLD; no order intent was created."],
            )
        risk_status = "BLOCKED" if gate.decision in {"REJECT", "ESCALATE"} else "WARNING" if gate.decision == "MODIFY" else "COMPLETE"
        timeline.append(
            _event(
                f"risk.{gate.decision.lower()}",
                f"Deterministic gate: {gate.decision}",
                gate.reasons[0] if gate.reasons else "Risk evaluation completed.",
                risk_status,
            )
        )

        if gate.decision in {"APPROVE", "MODIFY"}:
            status = "AWAITING_APPROVAL"
        elif gate.decision == "ESCALATE":
            status = "ESCALATED"
        else:
            status = "REJECTED"

        explanation = (
            build_hedge_explanation(
                request.symbol, decisions, consensus, hedge_plan, gate
            )
            if hedge_plan
            else build_explanation(
                request.symbol, decisions, consensus, proposal, gate
            )
        )
        timeline.append(_event("explanation.generated", "ExplainTrade record generated", "Votes, counter-evidence, risk changes, and invalidation conditions were captured."))
        alerts = run_soc_checks(
            run_id,
            request.symbol,
            request.scenario,
            consensus,
            proposal,
            gate,
            market,
            decisions,
            float(self.controls.values["max_new_position_pct"]),
            int(self.controls.values["max_data_age_seconds"]),
        )
        for alert in alerts:
            timeline.append(_event("soc.alert.created", alert.title, f"{alert.rule_id} · {alert.severity}: {alert.detail}", "WARNING"))

        result = WorkflowResult(
            workflow_run_id=run_id,
            symbol=request.symbol,
            status=status,
            mode=request.mode,
            scenario=request.scenario,
            agent_provider=actual_provider,
            strategy=request.strategy,
            replay_of=replay_of,
            created_at=started,
            completed_at=datetime.now(timezone.utc),
            market_snapshot=market,
            news_items=news,
            account=account,
            agent_decisions=decisions,
            consensus=consensus,
            risk_review=risk_review,
            proposal=proposal,
            hedge_plan=hedge_plan,
            risk_gate=gate,
            explanation=explanation,
            soc_alerts=alerts,
            timeline=timeline,
            errors=errors,
        )
        self.repository.save_workflow(result.model_dump(mode="json"))
        if request.auto_execute and self.settings.auto_execute_paper and status == "AWAITING_APPROVAL":
            return self.approve(run_id)
        return result

    def approve(self, run_id: str) -> WorkflowResult:
        with self.coordination.lock(f"approval:{run_id}"):
            return self._approve_locked(run_id)

    def _approve_locked(self, run_id: str) -> WorkflowResult:
        payload = self.repository.get_workflow(run_id, for_update=True)
        if not payload:
            raise KeyError(run_id)
        result = WorkflowResult.model_validate(payload)
        if result.status == "COMPLETED" and result.execution:
            return result
        if result.status != "AWAITING_APPROVAL" or not result.proposal:
            raise ValueError(f"workflow status {result.status} cannot be approved")

        # Re-evaluate at the moment of approval so policy changes, duplicate orders,
        # stale data, and the kill switch cannot be bypassed by an old verdict.
        if result.strategy == "PROTECTIVE_PUT":
            if result.hedge_plan is None:
                raise ValueError("protective-put workflow is missing its hedge plan")
            gate = HedgeRiskEngine(
                self.settings, self.controls, self.repository
            ).evaluate(
                run_id,
                result.hedge_plan,
                result.risk_review,
                result.market_snapshot,
                result.account,
                self.alpaca.clock(result.mode),
            )
        else:
            gate = RiskEngine(self.settings, self.controls, self.repository).evaluate(
                result.proposal,
                result.consensus,
                result.risk_review,
                result.market_snapshot,
                result.account,
                self.alpaca.clock(result.mode),
            )
        result.risk_gate = gate
        if gate.decision not in {"APPROVE", "MODIFY"}:
            result.status = "ESCALATED" if gate.decision == "ESCALATE" else "REJECTED"
            result.timeline.append(_event("approval.blocked", "Approval blocked on re-check", gate.reasons[0], "BLOCKED"))
            result.explanation = (
                build_hedge_explanation(
                    result.symbol,
                    result.agent_decisions,
                    result.consensus,
                    result.hedge_plan,
                    gate,
                )
                if result.hedge_plan
                else build_explanation(
                    result.symbol,
                    result.agent_decisions,
                    result.consensus,
                    result.proposal,
                    gate,
                )
            )
            self.repository.save_workflow(result.model_dump(mode="json"))
            return result

        order = self.alpaca.submit(result.proposal, gate, result.account.equity, result.mode)
        # Keep the order row and workflow transition in one database transaction.
        # The Redis approval lock remains held across the provider request and
        # commit, while PostgreSQL also holds the workflow row FOR UPDATE.
        self.repository.save_order(order.model_dump(mode="json"), commit=False)
        result.execution = order
        result.status = "COMPLETED"
        result.completed_at = datetime.now(timezone.utc)
        result.timeline.extend(
            [
                _event("order.submitted", "Paper order submitted", f"{order.execution_mode} · {order.provider_order_id}"),
                _event("workflow.completed", "Supervised workflow complete", "Execution and audit records are linked by workflow ID."),
            ]
        )
        result.explanation = (
            build_hedge_explanation(
                result.symbol,
                result.agent_decisions,
                result.consensus,
                result.hedge_plan,
                gate,
                order,
            )
            if result.hedge_plan
            else build_explanation(
                result.symbol,
                result.agent_decisions,
                result.consensus,
                result.proposal,
                gate,
                order,
            )
        )
        self.repository.save_workflow(result.model_dump(mode="json"))
        return result

    def reject(self, run_id: str) -> WorkflowResult:
        with self.coordination.lock(f"approval:{run_id}"):
            return self._reject_locked(run_id)

    def _reject_locked(self, run_id: str) -> WorkflowResult:
        payload = self.repository.get_workflow(run_id, for_update=True)
        if not payload:
            raise KeyError(run_id)
        result = WorkflowResult.model_validate(payload)
        if result.execution:
            raise ValueError("an executed workflow cannot be rejected")
        result.status = "REJECTED"
        result.timeline.append(_event("human.rejected", "Proposal rejected by reviewer", "No execution request was sent.", "BLOCKED"))
        self.repository.save_workflow(result.model_dump(mode="json"))
        return result

    def replay(self, run_id: str) -> WorkflowResult:
        payload = self.repository.get_workflow(run_id)
        if not payload:
            raise KeyError(run_id)
        prior = WorkflowResult.model_validate(payload)
        request = AnalysisRequest(
            symbol=prior.symbol,
            mode="REPLAY",
            scenario=prior.scenario,
            agent_provider="RULES",
            strategy=prior.strategy,
            auto_execute=False,
        )
        return self.analyze(request, replay_of=run_id)
