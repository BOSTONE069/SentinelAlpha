"use client";

import Link from "next/link";
import { useState } from "react";
import { Icon } from "@/components/icons";
import { MetricCard, PageHeader, Panel, ProgressRing, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import type { Workflow } from "@/lib/types";

const stages = ["Portfolio exposure", "Risk regime", "Option chain", "Hedge sizing", "RiskGate", "Audit record"];

export default function HedgingPage() {
  const [symbol, setSymbol] = useState("NVDA");
  const [provider, setProvider] = useState<"RULES" | "OPENAI">("RULES");
  const [mode, setMode] = useState<"REPLAY" | "LIVE">("REPLAY");
  const [autoExecute, setAutoExecute] = useState(false);
  const [run, setRun] = useState<Workflow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function analyze() {
    setLoading(true); setError(""); setRun(null);
    try { setRun(await api.analyzeHedge(symbol.trim().toUpperCase(), provider, mode, autoExecute)); }
    catch (err) { setError(err instanceof Error ? err.message : "Hedge analysis failed"); }
    finally { setLoading(false); }
  }

  async function approve() {
    if (!run?.hedge_plan?.contract) return;
    setLoading(true); setError("");
    try { setRun(await api.approve(run.workflow_run_id)); }
    catch (err) {
      if (run.mode === "REPLAY" && run.workflow_run_id.startsWith("demo-")) {
        setRun({ ...run, status: "COMPLETED", execution: { id: `ord-${Date.now()}`, provider_order_id: `sim-paper-${Date.now()}`, client_order_id: `sa-${run.symbol.toLowerCase()}-protective-put`, workflow_run_id: run.workflow_run_id, symbol: run.hedge_plan.contract.symbol, side: "BUY", notional: run.hedge_plan.estimated_premium, quantity: run.hedge_plan.contracts, status: "filled", execution_mode: "SIMULATED_PAPER", submitted_at: new Date().toISOString(), risk_decision: run.risk_gate.decision, instrument_type: "OPTION", underlying_symbol: run.symbol, order_type: "limit", limit_price: run.hedge_plan.limit_price, position_intent: "BUY_TO_OPEN", execution_interface: "SIMULATED_REPLAY" } });
      } else setError(err instanceof Error ? err.message : "Approval failed");
    } finally { setLoading(false); }
  }

  async function reject() {
    if (!run) return;
    try { setRun(await api.reject(run.workflow_run_id)); }
    catch { setRun({ ...run, status: "REJECTED" }); }
  }

  const plan = run?.hedge_plan;
  return <>
    <PageHeader eyebrow="Track 03 workflow" title="Portfolio Protection Agent" description="Detect portfolio risk, select and size a protective put, validate it through deterministic option controls, and route approved paper orders through Alpaca CLI." actions={<StatusPill value="PROTECTIVE PUT"/>}/>

    <Panel className="council-console">
      <div className="council-form hedge-form">
        <div className="symbol-field"><label>Underlying</label><div><span>$</span><input value={symbol} maxLength={8} onChange={(event) => setSymbol(event.target.value.replace(/[^A-Za-z.]/g, "").toUpperCase())} aria-label="Underlying stock symbol"/></div></div>
        <div className="field"><label>Options strategy</label><select className="select" value="PROTECTIVE_PUT" disabled><option>Protective put · adaptive hedge</option></select></div>
        <div className="field"><label>Data mode</label><div className="segmented"><button className={mode === "REPLAY" ? "active" : ""} onClick={() => setMode("REPLAY")}>REPLAY</button><button className={mode === "LIVE" ? "active" : ""} onClick={() => setMode("LIVE")}>LIVE ALPACA</button></div></div>
        <div className="field"><label>Agent engine</label><div className="segmented"><button className={provider === "RULES" ? "active" : ""} onClick={() => setProvider("RULES")}>STABLE DEMO</button><button className={provider === "OPENAI" ? "active" : ""} onClick={() => setProvider("OPENAI")}>OPENAI</button></div></div>
        <div className="field"><label>Execution</label><div className="segmented"><button className={!autoExecute ? "active" : ""} onClick={() => setAutoExecute(false)}>SUPERVISED</button><button className={autoExecute ? "active" : ""} onClick={() => setAutoExecute(true)}>AUTONOMOUS</button></div></div>
        <button className="button primary council-run" onClick={analyze} disabled={loading || !symbol}><Icon name="shield" size={15}/>{loading ? "ASSESSING…" : "ASSESS & DESIGN HEDGE"}</button>
      </div>
      <div className="console-note"><Icon name="lock" size={14}/><span>{autoExecute ? "Autonomous paper execution also requires AUTO_EXECUTE_PAPER=true on the API. It cannot bypass H001–H017 or submit live-money orders." : "Only protective puts on existing 100-share lots are eligible. Premium, spread, expiry, strike, duplicate, market-hours, and kill-switch controls fail closed."}</span></div>
    </Panel>

    {error && <div className="error-banner"><Icon name="shield" size={16}/><div><strong>Hedge workflow could not continue</strong><span>{error}</span></div></div>}
    {loading && <Panel className="workflow-loader"><div className="scan-line"/><div className="workflow-stages">{stages.map((stage, index) => <div key={stage} style={{ animationDelay: `${index * 130}ms` }}><span>{String(index + 1).padStart(2,"0")}</span><strong>{stage}</strong><em>processing</em></div>)}</div></Panel>}

    {run && plan && <div className="council-results hedge-results">
      <div className="metrics-grid">
        <MetricCard label="Portfolio risk" value={`${Math.round(plan.risk.score * 100)}/100`} footer={plan.risk.level} tone={plan.risk.level === "LOW" ? "good" : "warn"} icon="shield"/>
        <MetricCard label="Protected exposure" value={`${Math.round(plan.actual_hedge_ratio * 100)}%`} footer={`${plan.covered_shares.toLocaleString()} underlying shares`} icon="briefcase"/>
        <MetricCard label="Maximum premium" value={`$${plan.estimated_premium.toLocaleString()}`} footer={`${(plan.premium_pct_equity * 100).toFixed(2)}% of equity`} icon="order"/>
        <MetricCard label="Hedge decision" value={plan.action} footer={plan.execution_interface.replaceAll("_", " ")} tone={plan.action === "OPEN" ? "good" : "warn"} icon="decision"/>
      </div>

      <div className="split-65">
        <div className="stack">
          <Panel title="Protective-put proposal" kicker="Deterministic Hedge Agent">
            {plan.contract ? <div className="hedge-contract">
              <div className="hedge-contract-head"><div><span>OPTION CONTRACT</span><strong>{plan.contract.symbol}</strong></div><StatusPill value={run.risk_gate.decision}/></div>
              <div className="hedge-contract-grid">
                <div><span>Strategy</span><strong>Buy protective put</strong></div><div><span>Expiration</span><strong>{plan.contract.expiration_date}</strong></div><div><span>Strike</span><strong>${plan.contract.strike_price.toFixed(2)}</strong></div><div><span>Contracts</span><strong>{plan.contracts}</strong></div><div><span>Limit</span><strong>${plan.limit_price?.toFixed(2)}</strong></div><div><span>Bid / ask</span><strong>${plan.contract.bid_price.toFixed(2)} / ${plan.contract.ask_price.toFixed(2)}</strong></div>
              </div>
            </div> : <div className="no-execution"><Icon name="lock"/><strong>No eligible contract</strong><p>{plan.rationale[0]}</p></div>}
          </Panel>
          <Panel title="Why protection is active" kicker="ExplainHedge"><div className="factor-list positive-factors">{plan.rationale.map((reason) => <div key={reason}><span>+</span><p>{reason}</p></div>)}</div></Panel>
          <Panel title="Release and rebalance policy" kicker="Pre-committed lifecycle"><div className="invalidation-list">{[...plan.release_conditions, ...plan.rebalance_conditions].map((item, index) => <div key={item}><span>{String(index + 1).padStart(2,"0")}</span><p>{item}</p></div>)}</div></Panel>
        </div>
        <div className="stack">
          <Panel title="Risk composition" kicker="Adaptive activation score"><div className="hedge-score"><ProgressRing value={plan.risk.score} label="risk"/><div>{Object.entries(plan.risk.components).map(([key, value]) => <div key={key}><span>{key.replaceAll("_", " ")}</span><div><i style={{ width: `${value * 100}%` }}/></div><strong>{Math.round(value * 100)}</strong></div>)}</div></div></Panel>
          <Panel title="Option RiskGate" kicker={`${run.risk_gate.checks.length} deterministic checks`}><div className="rule-trace">{run.risk_gate.checks.map((check) => <div key={check.rule_id} className={check.passed ? "passed" : "failed"}><span>{check.passed ? "✓" : "!"}</span><div><strong>{check.rule_id} · {check.rule_name}</strong><p>{check.message}</p></div></div>)}</div></Panel>
        </div>
      </div>

      <div className="approval-bar"><div><Icon name="lock"/><span><strong>{run.status.replaceAll("_", " ")}</strong><em>{run.execution ? `${run.execution.execution_interface.replaceAll("_", " ")} · ${run.execution.provider_order_id}` : "No Alpaca option order occurs until the approved paper intent crosses the execution boundary."}</em></span></div><div>{!run.execution && run.status === "AWAITING_APPROVAL" && <><button className="button danger" onClick={reject}>Reject</button><button className="button primary" onClick={approve} disabled={loading}><Icon name="check" size={15}/>Approve protective put</button></>}<Link href={`/decisions/${run.workflow_run_id}`} className="button ghost">Full explanation<Icon name="arrow" size={14}/></Link></div></div>
    </div>}
  </>;
}
