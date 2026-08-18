"use client";

import { useEffect, useState } from "react";
import { PageHeader, Panel, StatusPill, ViewLink } from "@/components/ui";
import { api } from "@/lib/api";
import { demoRuns } from "@/lib/demo";
import type { Workflow } from "@/lib/types";

export default function DecisionsPage() {
  const [runs, setRuns] = useState<Workflow[]>(demoRuns);
  const [filter, setFilter] = useState("ALL");
  useEffect(() => { api.runs().then(setRuns); }, []);
  const visible = runs.filter((run) => filter === "ALL" || run.risk_gate.decision === filter);
  return <><PageHeader eyebrow="ExplainTrade + ExplainHedge" title="Decision ledger" description="Every council vote, hedge selection, policy verdict, and execution outcome remains linked to one immutable workflow ID." actions={<><a className="button ghost" href="/council">Equity analysis</a><a className="button primary" href="/hedging">New hedge</a></>}/>
    <Panel title="Supervised decisions" kicker={`${visible.length} audit-ready records`} action={<div className="segmented">{["ALL","MODIFY","REJECT","ESCALATE"].map((item) => <button key={item} className={filter === item ? "active" : ""} onClick={() => setFilter(item)}>{item}</button>)}</div>}>
      <div className="table-wrap"><table><thead><tr><th>Created</th><th>Symbol</th><th>Decision</th><th>Confidence</th><th>Agreement</th><th>Risk verdict</th><th>Exposure / hedge</th><th>Status</th><th></th></tr></thead><tbody>{visible.map((run) => <tr key={run.workflow_run_id}><td className="mono muted">{new Date(run.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</td><td><div className="symbol-cell"><span className="ticker-mark">{run.symbol.slice(0,2)}</span><div><strong>{run.symbol}</strong><div className="mono muted small truncate-id">{run.hedge_plan?.contract?.symbol ?? run.workflow_run_id}</div></div></div></td><td><StatusPill value={run.strategy === "PROTECTIVE_PUT" ? "BUY PUT" : run.consensus.direction}/></td><td className="mono"><strong>{Math.round(run.consensus.confidence * 100)}%</strong></td><td className="mono">{run.consensus.agreeing_agents}/{run.consensus.total_agents}</td><td><StatusPill value={run.risk_gate.decision}/></td><td className="mono">{run.hedge_plan ? `${run.hedge_plan.contracts} contract · ${Math.round(run.hedge_plan.actual_hedge_ratio * 100)}% covered` : `${Math.round(run.risk_gate.requested_position_pct*100)}% → ${Math.round(run.risk_gate.approved_position_pct*100)}%`}</td><td><StatusPill value={run.status}/></td><td><ViewLink href={`/decisions/${run.workflow_run_id}`} label="Explain"/></td></tr>)}</tbody></table></div>
    </Panel></>;
}
