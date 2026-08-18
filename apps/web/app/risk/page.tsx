"use client";

import { useEffect, useState } from "react";
import { Icon } from "@/components/icons";
import { PageHeader, Panel, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import { demoPolicies } from "@/lib/demo";
import type { RiskPolicy } from "@/lib/types";

function displayValue(policy: RiskPolicy) {
  if (policy.unit === "percent") return `${Math.round(Number(policy.value)*100)}%`;
  if (policy.unit === "boolean") return policy.value ? "ON" : "OFF";
  return `${policy.value}${policy.unit === "seconds" ? "s" : ""}`;
}

function percentMaximum(policy: RiskPolicy) {
  return ["confidence", "risk_score", "ratio", "spread"].some((part) => policy.key.includes(part)) ? 100 : 20;
}

export default function RiskPage() {
  const [policies, setPolicies] = useState<RiskPolicy[]>(demoPolicies);
  const [killSwitch, setKillSwitch] = useState(false);
  const [saved, setSaved] = useState("");
  useEffect(() => { Promise.all([api.policies(), api.riskStatus()]).then(([items,status]) => { setPolicies(items); setKillSwitch(status.kill_switch); }); }, []);
  async function update(policy: RiskPolicy, value: number | boolean) {
    setPolicies((items) => items.map((item) => item.key === policy.key ? { ...item, value } : item));
    try { const savedPolicy = await api.updatePolicy(policy.key, value); setPolicies((items) => items.map((item) => item.key === policy.key ? savedPolicy : item)); setSaved(policy.key); setTimeout(() => setSaved(""), 1600); } catch { setSaved(`${policy.key}:local`); }
  }
  return <><PageHeader eyebrow="Deterministic governance" title="Risk policies" description="These constraints are executable code, not suggestions in a prompt. Agents may propose; this policy set defines what can proceed." actions={<StatusPill value={killSwitch ? "KILL SWITCH ON" : "EXECUTION ENABLED"}/>}/>
    <div className={`kill-switch-panel ${killSwitch ? "engaged" : ""}`}><div className="kill-switch-icon"><Icon name="shield" size={26}/></div><div><span>GLOBAL EXECUTION CONTROL</span><h2>{killSwitch ? "Kill switch engaged" : "All policy-governed executions available"}</h2><p>{killSwitch ? "Every new order is blocked regardless of agent confidence." : "New paper orders may proceed only after all deterministic checks pass."}</p></div><button className={`button ${killSwitch ? "primary" : "danger"}`} onClick={() => api.setKillSwitch(!killSwitch).then((state) => setKillSwitch(state.kill_switch)).catch(() => setKillSwitch(!killSwitch))}>{killSwitch ? "Reset with review" : "Engage kill switch"}</button></div>
    <div className="risk-policy-grid">
      {policies.map((policy) => <Panel key={policy.key} className={`policy-card ${policy.locked ? "locked" : ""}`}><div className="policy-top"><div><span>{policy.label}</span><strong>{displayValue(policy)}</strong></div>{policy.locked ? <span className="lock-chip"><Icon name="lock" size={12}/>LOCKED</span> : saved.startsWith(policy.key) ? <span className="save-chip">✓ SAVED</span> : null}</div><p>{policy.description}</p>
        {policy.unit === "boolean" ? <button className={`toggle ${policy.value ? "on" : ""}`} disabled={policy.locked} onClick={() => update(policy,!policy.value)}><span/></button> : policy.unit === "percent" ? <div className="policy-control"><input type="range" min="0" max={percentMaximum(policy)} value={Math.round(Number(policy.value)*100)} disabled={policy.locked} onChange={(event) => update(policy,Number(event.target.value)/100)}/><div><span>0%</span><span>{percentMaximum(policy)}%</span></div></div> : <div className="stepper"><button disabled={policy.locked || Number(policy.value) <= 1} onClick={() => update(policy,Number(policy.value)-1)}>−</button><input value={Number(policy.value)} readOnly/><button disabled={policy.locked} onClick={() => update(policy,Number(policy.value)+1)}>+</button></div>}
        <div className="policy-key mono">{policy.key}</div></Panel>)}
    </div>
    <Panel title="Policy evaluation order" kicker="Fail-closed execution path" className="spaced-panel"><div className="policy-flow">{["Paper mode","Confidence","Agreement","Position limit","Buying power","Freshness","Duplicates","Trade count","Loss limit","Drawdown","Market hours","Semantic risk","Volatility","Shorting"].map((label,index,items) => <div key={label}><span>{String(index+1).padStart(2,"0")}</span><strong>{label}</strong>{index<items.length-1 && <i>→</i>}</div>)}</div></Panel>
    <Panel title="Protective-put evaluation" kicker="H001–H017 option controls" className="spaced-panel"><div className="policy-flow">{["Paper mode","100-share lot","Risk trigger","Put contract","DTE","Strike","Hedge size","Premium","Liquidity","Fresh quote","Duplicate","Trade count","Market hours","Semantic risk","Kill switch","Alpaca CLI","Options level"].map((label,index,items) => <div key={label}><span>{String(index+1).padStart(2,"0")}</span><strong>{label}</strong>{index<items.length-1 && <i>→</i>}</div>)}</div></Panel>
  </>;
}
