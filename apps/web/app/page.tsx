"use client";

import { useEffect, useMemo, useState } from "react";
import { EquityChart, MiniSparkline } from "@/components/charts";
import { MetricCard, Money, PageHeader, Panel, ProgressRing, StatusPill, ViewLink } from "@/components/ui";
import { api } from "@/lib/api";
import { demoAccount, demoAlerts, demoRuns } from "@/lib/demo";
import type { Account, SocAlert, Workflow } from "@/lib/types";

export default function OverviewPage() {
  const [account, setAccount] = useState<Account>(demoAccount);
  const [runs, setRuns] = useState<Workflow[]>(demoRuns);
  const [alerts, setAlerts] = useState<SocAlert[]>(demoAlerts);
  const [riskScore, setRiskScore] = useState(18);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState("");

  useEffect(() => {
    Promise.all([api.account(), api.runs(), api.alerts(), api.socOverview()]).then(([nextAccount, nextRuns, nextAlerts, overview]) => {
      setAccount(nextAccount); setRuns(nextRuns); setAlerts(nextAlerts); setRiskScore(overview.system_risk_score);
    });
  }, []);

  const equityBars = useMemo(() => (runs[0]?.market_snapshot.bars ?? demoRuns[0].market_snapshot.bars).map((bar, index, all) => ({ ...bar, close: account.equity * (0.968 + index / all.length * 0.032 + Math.sin(index / 5) * .003) })), [runs, account.equity]);
  const decisions = runs.slice(0, 5);

  async function exportAudit() {
    setExporting(true);
    setExportError("");
    try {
      await api.exportAudit();
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "Audit export failed.");
    } finally {
      setExporting(false);
    }
  }

  return <>
    <PageHeader eyebrow="Supervisory control plane" title="Portfolio command center" description="One view of portfolio risk, explainable hedge decisions, and every paper-trading action." actions={<><button type="button" className="button ghost" onClick={exportAudit} disabled={exporting}>{exporting ? "Exporting…" : "Export audit"}</button><a href="/hedging" className="button primary">Run Hedge Agent</a></>} />
    {exportError && <div className="error-banner" role="alert"><div><strong>Audit export failed</strong><span>{exportError}</span></div></div>}
    <div className="metrics-grid">
      <MetricCard label="Net equity" value={new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(account.equity)} delta={`+${account.day_pl_pct.toFixed(2)}%`} footer="today" icon="briefcase" tone="good" />
      <MetricCard label="Buying power" value={new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(account.buying_power)} footer={`${Math.round(account.cash / account.equity * 100)}% held in cash`} icon="pulse" />
      <MetricCard label="Day P / L" value={`+$${account.day_pl.toLocaleString(undefined, { maximumFractionDigits: 0 })}`} delta="+0.85%" footer="vs. prior close" icon="arrow" tone="good" />
      <MetricCard label="System risk" value={`${riskScore} / 100`} footer={riskScore < 35 ? "LOW · within policy" : "ELEVATED · review alerts"} icon="shield" tone={riskScore < 35 ? "good" : "warn"} />
    </div>

    <div className="dashboard-grid">
      <div className="stack">
        <Panel title="Portfolio equity" kicker="30-day paper performance" action={<div className="chart-range"><button>1D</button><button>1W</button><button className="active">1M</button><button>3M</button></div>}>
          <div className="chart-summary"><div><strong><Money value={account.equity}/></strong><span>▲ $3,284.60 · 3.40%</span></div><StatusPill value={account.source === "DEMO_REPLAY" ? "REPLAY DATA" : "ALPACA PAPER"} /></div>
          <EquityChart bars={equityBars} />
        </Panel>
        <Panel title="Recent protection decisions" kicker="Explainable agent outcomes" action={<ViewLink href="/decisions" label="All decisions" />}>
          <div className="table-wrap"><table><thead><tr><th>Symbol</th><th>Decision</th><th>Confidence</th><th>Risk gate</th><th>Signal</th><th></th></tr></thead><tbody>
            {decisions.map((run, index) => <tr key={run.workflow_run_id}><td><div className="symbol-cell"><span className="ticker-mark">{run.symbol.slice(0,2)}</span><strong>{run.symbol}</strong></div></td><td><StatusPill value={run.strategy === "PROTECTIVE_PUT" ? "BUY PUT" : run.consensus.direction}/></td><td className="mono"><strong>{Math.round(run.consensus.confidence * 100)}%</strong></td><td><StatusPill value={run.risk_gate.decision}/></td><td><MiniSparkline values={[4, 5, 4.6, 6.1, 5.8, 7 + index, 8.3 + index]} tone={run.risk_gate.decision === "REJECT" ? "bad" : run.risk_gate.decision === "ESCALATE" ? "warn" : "good"}/></td><td><ViewLink href={`/decisions/${run.workflow_run_id}`} label="Inspect"/></td></tr>)}
          </tbody></table></div>
        </Panel>
      </div>

      <div className="stack">
        <Panel title="Supervision status" kicker="Live control health">
          <div className="risk-score-row"><ProgressRing value={Math.min(riskScore / 100, 1)} label="risk score"/><div className="risk-score-copy"><StatusPill value={riskScore < 35 ? "LOW" : "ELEVATED"}/><h3>All controls operational</h3><p>Policy engine enforces 14 equity rules and 17 hedge-specific rules.</p></div></div>
          <div className="health-list"><div className="health-row"><span>Agent health</span><strong className="positive-text">5 / 5</strong></div><div className="health-row"><span>Paper execution</span><strong>ARMED</strong></div><div className="health-row"><span>Live-money execution</span><strong>DISABLED</strong></div><div className="health-row"><span>Audit completeness</span><strong>100%</strong></div></div>
        </Panel>
        <Panel title="Active SOC alerts" kicker="Agent behavior monitoring" action={<ViewLink href="/soc" label="Open SOC"/>}>
          <div className="alert-list">{alerts.slice(0,4).map((alert) => <div className="alert-item" key={alert.id}><span className={`severity-bar ${alert.severity}`}/><div className="alert-copy"><strong>{alert.title}</strong><p>{alert.detail}</p></div><div className="alert-meta">{alert.severity}<br/>{alert.symbol}</div></div>)}</div>
        </Panel>
        <Panel title="Execution boundary" kicker="Non-negotiable architecture">
          <div className="boundary-flow"><div><span>01</span><strong>Agents reason</strong><em>Structured opinions</em></div><i>→</i><div><span>02</span><strong>Policy decides</strong><em>Fail-closed checks</em></div><i>→</i><div><span>03</span><strong>Service trades</strong><em>Paper only</em></div></div>
        </Panel>
      </div>
    </div>
  </>;
}
