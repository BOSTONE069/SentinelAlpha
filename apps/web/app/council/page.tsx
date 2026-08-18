"use client";

import Link from "next/link";
import { useState } from "react";
import { Icon } from "@/components/icons";
import { PageHeader, Panel, ProgressRing, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import type { Workflow } from "@/lib/types";

const agentCodes: Record<string, string> = { market: "MKT", news: "NWS", quant: "QNT", portfolio: "PRT" };
const stages = ["Market data", "News intelligence", "Quant features", "Four agent votes", "Consensus", "Risk gate"];

export default function CouncilPage() {
  const [symbol, setSymbol] = useState("AAPL");
  const [scenario, setScenario] = useState("risk_modification");
  const [provider, setProvider] = useState<"RULES" | "OPENAI">("RULES");
  const [mode, setMode] = useState<"REPLAY" | "LIVE">("REPLAY");
  const [run, setRun] = useState<Workflow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function analyze() {
    setLoading(true); setError(""); setRun(null);
    try { setRun(await api.analyze(symbol.trim().toUpperCase(), scenario, provider, mode)); }
    catch (err) { setError(err instanceof Error ? err.message : "Analysis failed"); }
    finally { setLoading(false); }
  }

  async function approve() {
    if (!run) return;
    setLoading(true); setError("");
    try { setRun(await api.approve(run.workflow_run_id)); }
    catch (err) {
      if (run.mode === "REPLAY" && run.workflow_run_id.startsWith("demo-")) {
        setRun({ ...run, status: "COMPLETED", execution: { id: `ord-${Date.now()}`, provider_order_id: `sim-paper-${Date.now()}`, client_order_id: `sa-${run.symbol.toLowerCase()}-buy`, workflow_run_id: run.workflow_run_id, symbol: run.symbol, side: "BUY", notional: run.account.equity * run.risk_gate.approved_position_pct, status: "filled", execution_mode: "SIMULATED_PAPER", submitted_at: new Date().toISOString(), risk_decision: run.risk_gate.decision, instrument_type: "EQUITY", order_type: "market", execution_interface: "SIMULATED_REPLAY" } });
      } else setError(err instanceof Error ? err.message : "Approval failed");
    } finally { setLoading(false); }
  }

  async function reject() {
    if (!run) return;
    try { setRun(await api.reject(run.workflow_run_id)); }
    catch { setRun({ ...run, status: "REJECTED" }); }
  }

  return <>
    <PageHeader eyebrow="Hero workflow" title="Agent Council" description="Independent analytical agents evaluate one symbol. Code combines their votes; deterministic policy controls what is permissible." actions={<StatusPill value="PAPER MODE LOCKED"/>}/>
    <Panel className="council-console">
      <div className="council-form">
        <div className="symbol-field"><label>Security</label><div><span>$</span><input value={symbol} maxLength={8} onChange={(event) => setSymbol(event.target.value.replace(/[^A-Za-z.]/g, "").toUpperCase())} aria-label="Stock symbol"/></div></div>
        <div className="field"><label>Demo scenario</label><select className="select" value={scenario} onChange={(event) => setScenario(event.target.value)}><option value="risk_modification">Risk modification · 8% → 4%</option><option value="information_risk">Information-risk escalation</option><option value="agent_soc">Agent behavior anomaly</option></select></div>
        <div className="field"><label>Data mode</label><div className="segmented"><button className={mode === "REPLAY" ? "active" : ""} onClick={() => setMode("REPLAY")}>REPLAY</button><button className={mode === "LIVE" ? "active" : ""} onClick={() => setMode("LIVE")}>LIVE ALPACA</button></div></div>
        <div className="field"><label>Agent engine</label><div className="segmented"><button className={provider === "RULES" ? "active" : ""} onClick={() => setProvider("RULES")}>STABLE DEMO</button><button className={provider === "OPENAI" ? "active" : ""} onClick={() => setProvider("OPENAI")}>OPENAI</button></div></div>
        <button className="button primary council-run" onClick={analyze} disabled={loading || !symbol}><Icon name="play" size={15}/>{loading ? "ORCHESTRATING…" : "RUN AGENT COUNCIL"}</button>
      </div>
      <div className="console-note"><Icon name="shield" size={14}/><span>Agents cannot call the broker. Their output is schema-validated before consensus and risk evaluation.</span></div>
    </Panel>

    {error && <div className="error-banner"><Icon name="shield" size={16}/><div><strong>Workflow could not continue</strong><span>{error}</span></div></div>}

    {loading && <Panel className="workflow-loader"><div className="scan-line"/><div className="workflow-stages">{stages.map((stage, index) => <div key={stage} style={{ animationDelay: `${index * 130}ms` }}><span>{String(index + 1).padStart(2,"0")}</span><strong>{stage}</strong><em>processing</em></div>)}</div></Panel>}

    {run && <div className="council-results">
      <div className="results-heading"><div><div className="eyebrow">Workflow {run.workflow_run_id.slice(0,8)}</div><h2>{run.symbol} council verdict</h2></div><div className="source-label"><span className="status-dot positive"/>{run.market_snapshot.source.replaceAll("_", " ")} · {run.agent_provider}</div></div>
      <div className="agent-grid">{run.agent_decisions.map((decision) => <div className={`agent-card action-${decision.action.toLowerCase()}`} key={decision.agent_name}><div className="agent-card-top"><span className="agent-code">{agentCodes[decision.agent_name]}</span><StatusPill value={decision.action}/></div><div className="agent-card-title"><h3>{decision.display_name}</h3><strong>{Math.round(decision.confidence * 100)}<small>%</small></strong></div><p>{decision.thesis}</p><div className="confidence-track"><span style={{ width: `${decision.confidence * 100}%` }}/></div><div className="agent-evidence"><span>{decision.evidence[0]?.label}</span><strong>{decision.evidence[0]?.value}</strong></div><div className="agent-footer"><span>{decision.engine}</span><span>{decision.latency_ms || "—"} ms</span></div></div>)}</div>

      <div className="decision-rail">
        <Panel title="Code-derived consensus" kicker="No LLM aggregation" className="consensus-panel"><div className="consensus-layout"><ProgressRing value={run.consensus.confidence} label="confidence"/><div className="consensus-action"><StatusPill value={run.consensus.direction}/><strong>{run.consensus.direction}</strong><span>Weighted score <em>{run.consensus.weighted_score > 0 ? "+" : ""}{run.consensus.weighted_score.toFixed(3)}</em></span></div><div className="vote-count"><strong>{run.consensus.agreeing_agents}/{run.consensus.total_agents}</strong><span>agents agree</span><div>{run.consensus.supporting_agents.map((agent) => <i key={agent}/>)}</div></div></div></Panel>
        <Panel title="Risk & Security" kicker="Deterministic policy verdict" className={`gate-panel gate-${run.risk_gate.decision.toLowerCase()}`}><div className="gate-layout"><div><StatusPill value={run.risk_gate.decision}/><h3>{run.risk_gate.decision === "MODIFY" ? "Approved with controls" : run.risk_gate.decision === "ESCALATE" ? "Human review required" : "Execution blocked"}</h3><p>{run.risk_gate.reasons[0]}</p></div><div className="size-change"><span><em>REQUESTED</em><strong>{Math.round(run.risk_gate.requested_position_pct * 100)}%</strong></span><Icon name="arrow"/><span><em>APPROVED</em><strong>{Math.round(run.risk_gate.approved_position_pct * 100)}%</strong></span></div></div><div className="check-strip">{run.risk_gate.checks.slice(0,6).map((check) => <div key={check.rule_id} className={check.passed ? "pass" : "fail"}><span>{check.passed ? "✓" : "!"}</span><strong>{check.rule_id}</strong><em>{check.rule_name}</em></div>)}</div></Panel>
      </div>

      <div className="approval-bar"><div><Icon name="lock"/><span><strong>{run.status.replaceAll("_", " ")}</strong><em>{run.execution ? `${run.execution.execution_mode} · ${run.execution.provider_order_id}` : "No broker action occurs until a human approves this paper intent."}</em></span></div><div>{!run.execution && run.status === "AWAITING_APPROVAL" && <><button className="button danger" onClick={reject}>Reject</button><button className="button primary" onClick={approve} disabled={loading}><Icon name="check" size={15}/>Approve paper trade</button></>}<Link href={`/decisions/${run.workflow_run_id}`} className="button ghost">Full explanation<Icon name="arrow" size={14}/></Link></div></div>
    </div>}
  </>;
}
