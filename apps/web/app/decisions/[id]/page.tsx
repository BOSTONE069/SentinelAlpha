"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Icon } from "@/components/icons";
import { PageHeader, Panel, ProgressRing, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import type { Workflow } from "@/lib/types";

export default function DecisionDetailPage() {
  const params = useParams<{ id: string }>();
  const [run, setRun] = useState<Workflow | null>(null);
  useEffect(() => { api.run(params.id).then(setRun); }, [params.id]);
  if (!run) return <div className="detail-loading"><div className="skeleton loading"/><div className="skeleton loading"/></div>;
  const hedge = run.hedge_plan;
  return <>
    <PageHeader eyebrow={`Workflow ${run.workflow_run_id}`} title={run.explanation.headline} description={run.explanation.summary} actions={<><StatusPill value={run.mode === "REPLAY" ? "REPLAY DATA" : "LIVE DATA"}/><button className="button ghost" onClick={() => api.replay(run.workflow_run_id).then(setRun)}>Replay analysis</button></>}/>
    <div className="decision-hero">
      <div className="decision-symbol"><span>{run.symbol.slice(0,2)}</span><div><em>{run.symbol}</em><strong>${run.market_snapshot.price.toFixed(2)}</strong><small className={run.market_snapshot.change_pct >= 0 ? "positive-text" : "negative-text"}>{run.market_snapshot.change_pct >= 0 ? "+" : ""}{(run.market_snapshot.change_pct*100).toFixed(2)}%</small></div></div>
      <div className="decision-stat"><span>FINAL ACTION</span><StatusPill value={hedge?.action ?? run.consensus.direction}/><strong>{hedge ? `${hedge.action} PUT` : run.consensus.direction}</strong></div>
      <div className="decision-stat"><span>{hedge ? "PORTFOLIO RISK" : "COUNCIL CONFIDENCE"}</span><ProgressRing value={hedge?.risk.score ?? run.consensus.confidence} size={75}/></div>
      <div className="decision-stat"><span>RISK DECISION</span><StatusPill value={run.risk_gate.decision}/><strong>{run.risk_gate.decision}</strong></div>
      <div className="decision-size"><span><em>{hedge ? "TARGET HEDGE" : "REQUESTED"}</em><strong>{Math.round((hedge?.target_hedge_ratio ?? run.risk_gate.requested_position_pct)*100)}%</strong></span><Icon name="arrow"/><span><em>{hedge ? "ACTUAL HEDGE" : "PERMITTED"}</em><strong>{Math.round((hedge?.actual_hedge_ratio ?? run.risk_gate.approved_position_pct)*100)}%</strong></span></div>
    </div>

    <div className="split-65">
      <div className="stack">
        {hedge?.contract && <Panel title="Selected protective put" kicker="Hedge Agent output"><div className="hedge-contract"><div className="hedge-contract-head"><div><span>OPTION CONTRACT</span><strong>{hedge.contract.symbol}</strong></div><StatusPill value={hedge.action}/></div><div className="hedge-contract-grid"><div><span>Expiration</span><strong>{hedge.contract.expiration_date}</strong></div><div><span>Strike</span><strong>${hedge.contract.strike_price.toFixed(2)}</strong></div><div><span>Quantity</span><strong>{hedge.contracts} contract(s)</strong></div><div><span>Limit</span><strong>${hedge.limit_price?.toFixed(2)}</strong></div><div><span>Premium</span><strong>${hedge.estimated_premium.toLocaleString()}</strong></div><div><span>Interface</span><strong>{hedge.execution_interface.replaceAll("_", " ")}</strong></div></div></div></Panel>}
        <Panel title={hedge ? "Why the agent opened protection" : "Why the council leaned bullish"} kicker="Supporting evidence"><div className="factor-list positive-factors">{run.explanation.positive_factors.map((factor) => <div key={factor}><span>+</span><p>{factor}</p></div>)}</div></Panel>
        <Panel title="Counter-evidence" kicker="What the decision did not ignore"><div className="factor-list negative-factors">{run.explanation.negative_factors.map((factor) => <div key={factor}><span>−</span><p>{factor}</p></div>)}</div></Panel>
        <Panel title="Agent vote matrix" kicker="Independent analytical sleeves"><div className="vote-matrix">{run.agent_decisions.map((decision) => <div key={decision.agent_name}><div className="vote-agent"><span>{decision.agent_name.slice(0,3).toUpperCase()}</span><div><strong>{decision.display_name}</strong><em>{decision.engine}</em></div></div><StatusPill value={decision.action}/><strong className="vote-confidence">{Math.round(decision.confidence*100)}%</strong><p>{decision.thesis}</p></div>)}</div><div className="consensus-note"><Icon name="decision"/><p>{run.explanation.consensus_explanation}</p></div></Panel>
        <Panel title={hedge ? "When protection will be released" : "What would invalidate this trade?"} kicker="Pre-committed exit logic"><div className="invalidation-list">{run.explanation.invalidation_conditions.map((item, index) => <div key={item}><span>{String(index+1).padStart(2,"0")}</span><p>{item}</p></div>)}</div></Panel>
      </div>
      <div className="stack">
        <Panel title="Risk rule trace" kicker={`${run.risk_gate.checks.length} deterministic checks`}><div className="rule-trace">{run.risk_gate.checks.map((check) => <div key={check.rule_id} className={check.passed ? "passed" : "failed"}><span>{check.passed ? "✓" : "!"}</span><div><strong>{check.rule_id} · {check.rule_name}</strong><p>{check.message}</p></div></div>)}</div></Panel>
        <Panel title="Semantic review" kicker="Independent Risk & Security Agent"><div className="semantic-review"><div><StatusPill value={run.risk_review.verdict}/><strong>{Math.round(run.risk_review.semantic_risk_score*100)}/100</strong></div><p>{run.risk_review.explanation}</p>{run.risk_review.issues.length > 0 && <div className="tag-list">{run.risk_review.issues.map((issue) => <span key={issue}>{issue.replaceAll("_"," ")}</span>)}</div>}</div></Panel>
        <Panel title="Execution record" kicker="What actually reached the broker">{run.execution ? <div className="execution-record"><StatusPill value={run.execution.status}/><div><span>Mode / interface</span><strong>{run.execution.execution_mode.replaceAll("_"," ")} · {run.execution.execution_interface.replaceAll("_", " ")}</strong></div><div><span>{run.execution.instrument_type === "OPTION" ? "Premium / quantity" : "Notional"}</span><strong>${run.execution.notional.toLocaleString()}{run.execution.quantity ? ` · ${run.execution.quantity} contract(s)` : ""}</strong></div>{run.execution.limit_price && <div><span>Limit price</span><strong>${run.execution.limit_price.toFixed(2)}</strong></div>}<div><span>Provider ID</span><strong className="mono">{run.execution.provider_order_id}</strong></div></div> : <div className="no-execution"><Icon name="lock"/><strong>No execution submitted</strong><p>This workflow remains blocked or awaits explicit paper-trade approval.</p></div>}</Panel>
      </div>
    </div>
  </>;
}
