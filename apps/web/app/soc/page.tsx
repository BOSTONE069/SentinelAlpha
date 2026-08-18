"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/icons";
import { MetricCard, PageHeader, Panel, ProgressRing, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import { demoAlerts } from "@/lib/demo";
import type { SocAlert } from "@/lib/types";

const agents = [
  ["Market Intelligence", "182 ms", "99.8%"], ["News Intelligence", "246 ms", "99.2%"], ["Quant Strategy", "94 ms", "100%"], ["Portfolio Manager", "137 ms", "99.7%"], ["Risk & Security", "112 ms", "100%"],
];

export default function SocPage() {
  const [alerts, setAlerts] = useState<SocAlert[]>(demoAlerts);
  const [overview, setOverview] = useState({ system_risk_score: 18, active_alerts: 3, trades_blocked_today: 4, agent_health: { healthy: 5, total: 5 }, kill_switch: false });
  const [severity, setSeverity] = useState("ALL");
  useEffect(() => { Promise.all([api.alerts(), api.socOverview()]).then(([a,o]) => { setAlerts(a); setOverview(o); }); }, []);
  const visible = alerts.filter((alert) => severity === "ALL" || alert.severity === severity);
  return <>
    <PageHeader eyebrow="Trading Agent SOC" title="Behavioral security operations" description="SentinelAlpha watches the agents themselves: stale inputs, sizing anomalies, repeated attempts, disagreement, and tool-use bursts." actions={<><StatusPill value={overview.kill_switch ? "KILL SWITCH ON" : "EXECUTION MONITORED"}/><button className="button danger" onClick={() => api.setKillSwitch(!overview.kill_switch).then((state) => setOverview({ ...overview, kill_switch: state.kill_switch }))}>{overview.kill_switch ? "Reset kill switch" : "Engage kill switch"}</button></>}/>
    <div className="metrics-grid">
      <MetricCard label="System risk score" value={`${overview.system_risk_score} / 100`} footer={overview.system_risk_score < 35 ? "LOW · controlled" : "ELEVATED"} icon="shield" tone={overview.system_risk_score < 35 ? "good" : "warn"}/>
      <MetricCard label="Agent health" value={`${overview.agent_health.healthy} / ${overview.agent_health.total}`} footer="all sleeves reporting" icon="pulse" tone="good"/>
      <MetricCard label="Active alerts" value={String(overview.active_alerts)} footer="requires triage" icon="bell" tone="warn"/>
      <MetricCard label="Trades blocked" value={String(overview.trades_blocked_today)} footer="today by policy" icon="lock" tone="good"/>
    </div>
    <div className="split-65">
      <div className="stack">
        <Panel title="Security alert queue" kicker="Rule-based explainable detections" action={<div className="segmented">{["ALL","CRITICAL","HIGH","MEDIUM","LOW"].map((value) => <button key={value} className={severity === value ? "active" : ""} onClick={() => setSeverity(value)}>{value}</button>)}</div>}>
          <div className="soc-alert-table">{visible.map((alert) => <div key={alert.id} className="soc-alert-row"><span className={`alert-icon ${alert.severity}`}><Icon name={alert.severity === "CRITICAL" || alert.severity === "HIGH" ? "shield" : "pulse"}/></span><div className="soc-alert-main"><div><StatusPill value={alert.severity}/><span className="mono">{alert.rule_id}</span><span>{alert.alert_type.replaceAll("_"," ")}</span></div><strong>{alert.title}</strong><p>{alert.detail}</p></div><div className="soc-alert-side"><span>{alert.symbol ?? "SYSTEM"}</span><em>{new Date(alert.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</em><button className="button compact ghost" onClick={() => setAlerts((items) => items.map((item) => item.id === alert.id ? { ...item, status: "ACKNOWLEDGED" } : item))}>{alert.status === "OPEN" ? "Acknowledge" : alert.status}</button></div></div>)}</div>
        </Panel>
        <Panel title="Detection coverage" kicker="10 active SOC rules"><div className="coverage-grid">{[["SOC001","Agent disagreement"],["SOC002","Low-confidence intent"],["SOC003","Oversized proposal"],["SOC004","Repeated rejections"],["SOC005","Stale market input"],["SOC006","Sentiment spike"],["SOC007","Latency anomaly"],["SOC008","Tool invocation burst"],["SOC009","Duplicate intent"],["SOC010","Policy tampering"]].map(([code,name]) => <div key={code}><span className="online-dot"/><strong>{code}</strong><em>{name}</em></div>)}</div></Panel>
      </div>
      <div className="stack">
        <Panel title="System posture" kicker="Continuous assessment"><div className="posture"><ProgressRing value={overview.system_risk_score/100} size={135} label="system risk"/><StatusPill value={overview.system_risk_score < 35 ? "LOW" : "ELEVATED"}/><h3>Controls are containing observed risk</h3><p>Open alerts describe agent or information behavior. They are signals for review, not claims of market manipulation.</p></div></Panel>
        <Panel title="Agent health" kicker="Latency and schema success"><div className="agent-health-table"><div className="agent-health-head"><span>Agent</span><span>Latency</span><span>Valid</span></div>{agents.map(([name,latency,rate]) => <div key={name}><span><i className="online-dot"/>{name}</span><strong>{latency}</strong><strong>{rate}</strong></div>)}</div></Panel>
        <Panel title="Security boundary" kicker="Fail-closed state"><div className="security-state"><div><span>News prompt isolation</span><StatusPill value="ACTIVE"/></div><div><span>Structured output validation</span><StatusPill value="ACTIVE"/></div><div><span>Broker tool access for agents</span><StatusPill value="DENIED"/></div><div><span>Live trading</span><StatusPill value="DISABLED"/></div></div></Panel>
      </div>
    </div>
  </>;
}
