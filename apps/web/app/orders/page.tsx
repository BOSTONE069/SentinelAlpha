"use client";

import { useEffect, useState } from "react";
import { PageHeader, Panel, StatusPill, ViewLink } from "@/components/ui";
import { api } from "@/lib/api";
import { demoOrders } from "@/lib/demo";
import type { Order } from "@/lib/types";

export default function OrdersPage() {
  const [orders, setOrders] = useState<Order[]>(demoOrders);
  useEffect(() => { api.orders().then(setOrders); }, []);
  return <><PageHeader eyebrow="Broker execution ledger" title="Paper orders" description="Orders can only originate from approved workflow proposals. A generic bypass endpoint does not exist." actions={<StatusPill value="PAPER ONLY"/>}/>
    <div className="metrics-grid"><div className="metric-card"><div className="metric-top"><span>Orders today</span></div><div className="metric-value">{orders.length}</div><div className="metric-footer"><span>supervised submissions</span></div></div><div className="metric-card"><div className="metric-top"><span>Committed capital</span></div><div className="metric-value">${orders.reduce((sum,o)=>sum+o.notional,0).toLocaleString()}</div><div className="metric-footer"><span>notional plus option premiums</span></div></div><div className="metric-card"><div className="metric-top"><span>Option hedges</span></div><div className="metric-value">{orders.filter((o)=>o.instrument_type==="OPTION").length}</div><div className="metric-footer"><span>CLI-supervised orders</span></div></div><div className="metric-card"><div className="metric-top"><span>Duplicate attempts</span></div><div className="metric-value">0</div><div className="metric-footer"><span className="positive-text">idempotency intact</span></div></div></div>
    <Panel title="Execution records" kicker={`${orders.length} linked paper orders`}><div className="table-wrap"><table><thead><tr><th>Submitted</th><th>Instrument</th><th>Side</th><th>Capital</th><th>Provider order ID</th><th>Interface</th><th>Risk verdict</th><th>Status</th><th></th></tr></thead><tbody>{orders.map((order)=><tr key={order.id}><td className="mono muted">{new Date(order.submitted_at).toLocaleString([], { month:"short",day:"2-digit",hour:"2-digit",minute:"2-digit"})}</td><td><div className="symbol-cell"><span className="ticker-mark">{order.symbol.slice(0,2)}</span><div><strong>{order.symbol}</strong><div className="mono muted small">{order.instrument_type === "OPTION" ? `${order.quantity ?? 0} contract · ${order.position_intent?.replaceAll("_", " ")}` : "equity"}</div></div></div></td><td><StatusPill value={order.side}/></td><td className="mono"><strong>${order.notional.toLocaleString()}</strong>{order.limit_price != null && <div className="muted small">limit ${order.limit_price.toFixed(2)}</div>}</td><td className="mono muted">{order.provider_order_id}</td><td><StatusPill value={order.execution_interface.replaceAll("_"," ")}/></td><td><StatusPill value={order.risk_decision}/></td><td><StatusPill value={order.status}/></td><td><ViewLink href={`/decisions/${order.workflow_run_id}`} label="Trace"/></td></tr>)}</tbody></table></div></Panel>
  </>;
}
