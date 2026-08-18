"use client";

import { useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/icons";
import { PageHeader, Panel, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import { demoRuns } from "@/lib/demo";
import type { Workflow } from "@/lib/types";

export default function AuditPage() {
  const [runs,setRuns] = useState<Workflow[]>(demoRuns);
  const [selected,setSelected] = useState<Workflow>(demoRuns[0]);
  const [query,setQuery] = useState("");
  const [exporting,setExporting] = useState(false);
  const [exportError,setExportError] = useState("");
  useEffect(()=>{api.runs().then((items)=>{setRuns(items);setSelected(items[0]??demoRuns[0]);});},[]);
  const visible = useMemo(()=>runs.filter((run)=>`${run.symbol} ${run.workflow_run_id}`.toLowerCase().includes(query.toLowerCase())),[runs,query]);
  async function exportSelected() {
    setExporting(true);
    setExportError("");
    try {
      await api.exportAudit(selected.workflow_run_id);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "Audit export failed.");
    } finally {
      setExporting(false);
    }
  }
  return <><PageHeader eyebrow="Immutable traceability" title="Audit explorer" description="Replay the exact path from input snapshot through individual votes, policy evaluation, execution, and SOC monitoring." actions={<button type="button" className="button ghost" onClick={exportSelected} disabled={exporting}>{exporting ? "Exporting…" : "Export JSON"}</button>}/>
    {exportError && <div className="error-banner" role="alert"><Icon name="shield" size={16}/><div><strong>Audit export failed</strong><span>{exportError}</span></div></div>}
    <div className="audit-layout">
      <Panel title="Workflow records" kicker={`${visible.length} searchable runs`}><div className="audit-search"><Icon name="search" size={15}/><input value={query} onChange={(event)=>setQuery(event.target.value)} placeholder="Search symbol or run ID"/></div><div className="run-list">{visible.map((run)=><button key={run.workflow_run_id} className={selected.workflow_run_id===run.workflow_run_id?"active":""} onClick={()=>setSelected(run)}><span className="ticker-mark">{run.symbol.slice(0,2)}</span><div><strong>{run.symbol} · {run.consensus.direction}</strong><em>{new Date(run.created_at).toLocaleString()}</em><small className="mono">{run.workflow_run_id}</small></div><StatusPill value={run.risk_gate.decision}/></button>)}</div></Panel>
      <Panel title={`${selected.symbol} workflow timeline`} kicker={selected.workflow_run_id} action={<button className="button compact" onClick={()=>api.replay(selected.workflow_run_id).then((run)=>{setRuns((items)=>[run,...items]);setSelected(run);})}><Icon name="play" size={12}/>Replay safely</button>}>
        <div className="audit-summary"><div><span>Source</span><strong>{selected.market_snapshot.source.replaceAll("_"," ")}</strong></div><div><span>Agents</span><strong>{selected.agent_provider}</strong></div><div><span>Council</span><StatusPill value={selected.consensus.direction}/></div><div><span>Risk</span><StatusPill value={selected.risk_gate.decision}/></div><div><span>Execution</span><strong>{selected.execution?.status ?? "NONE"}</strong></div></div>
        <div className="timeline">{selected.timeline.map((event,index)=><div key={event.id} className={`timeline-event ${event.status.toLowerCase()}`}><div className="timeline-time">{new Date(event.timestamp).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit",second:"2-digit"})}</div><div className="timeline-node"><span>{event.status==="COMPLETE"?"✓":event.status==="BLOCKED"?"!":"•"}</span>{index<selected.timeline.length-1&&<i/>}</div><div className="timeline-copy"><em>{event.event}</em><strong>{event.title}</strong><p>{event.detail}</p></div></div>)}</div>
        <div className="audit-proof"><Icon name="lock"/><div><strong>Replay cannot submit an order</strong><p>Stored inputs are re-analyzed under current policy and always force auto_execute=false.</p></div></div>
      </Panel>
    </div>
  </>;
}
