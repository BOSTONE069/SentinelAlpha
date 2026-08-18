"use client";

import { useEffect, useState } from "react";
import { AllocationDonut, MiniSparkline } from "@/components/charts";
import { MetricCard, Money, PageHeader, Panel, StatusPill } from "@/components/ui";
import { api } from "@/lib/api";
import { demoAccount } from "@/lib/demo";
import type { Account } from "@/lib/types";

export default function PortfolioPage() {
  const [account, setAccount] = useState<Account>(demoAccount);
  useEffect(() => { api.account().then(setAccount); }, []);
  return <><PageHeader eyebrow="Alpaca paper account" title="Portfolio & exposure" description="Current holdings are context for the Portfolio Manager Agent and hard inputs to every sizing rule." actions={<StatusPill value={account.source.replaceAll("_", " ")}/>}/>
    <div className="metrics-grid"><MetricCard label="Total equity" value={new Intl.NumberFormat("en-US",{style:"currency",currency:"USD",maximumFractionDigits:0}).format(account.equity)} delta="+3.40%" footer="30 days" icon="briefcase" tone="good"/><MetricCard label="Cash" value={new Intl.NumberFormat("en-US",{style:"currency",currency:"USD",maximumFractionDigits:0}).format(account.cash)} footer={`${Math.round(account.cash/account.equity*100)}% liquidity`} icon="pulse"/><MetricCard label="Buying power" value={new Intl.NumberFormat("en-US",{style:"currency",currency:"USD",maximumFractionDigits:0}).format(account.buying_power)} footer="paper leverage available" icon="arrow"/><MetricCard label="Unrealized P / L" value={`+$${account.positions.reduce((sum,p) => sum+p.unrealized_pl,0).toLocaleString(undefined,{maximumFractionDigits:0})}`} footer="across open positions" icon="decision" tone="good"/></div>
    <div className="grid-2">
      <Panel title="Asset allocation" kicker="Concentration context"><AllocationDonut positions={account.positions}/><div className="concentration-note"><StatusPill value="WITHIN LIMITS"/><p>Largest symbol exposure is {Math.max(...account.positions.map((p) => p.weight)).toFixed(0)}%; policy cap is 10%.</p></div></Panel>
      <Panel title="Risk utilization" kicker="Capacity before new exposure"><div className="utilization-list"><div><span><em>Single-symbol utilization</em><strong>80%</strong></span><div><i style={{width:"80%"}}/></div><small>NVDA 8% / 10% cap</small></div><div><span><em>Daily loss budget</em><strong>0%</strong></span><div><i style={{width:"2%"}}/></div><small>+$842 P/L / −$3,000 stop</small></div><div><span><em>Trade-count budget</em><strong>30%</strong></span><div><i style={{width:"30%"}}/></div><small>{account.trades_today} / 10 executions</small></div><div><span><em>Drawdown budget</em><strong>15%</strong></span><div><i style={{width:"15%"}}/></div><small>{account.portfolio_drawdown_pct.toFixed(1)}% / 8% kill threshold</small></div></div></Panel>
    </div>
    <Panel title="Open positions" kicker={`${account.positions.length} holdings · ${Math.round(account.positions.reduce((sum,p)=>sum+p.weight,0)*100)}% invested`} className="spaced-panel">
      <div className="table-wrap"><table><thead><tr><th>Symbol</th><th>Quantity</th><th>Market value</th><th>Avg. entry</th><th>Last</th><th>Weight</th><th>Unrealized P/L</th><th>30D signal</th></tr></thead><tbody>{account.positions.map((position,index) => <tr key={position.symbol}><td><div className="symbol-cell"><span className="ticker-mark">{position.symbol.slice(0,2)}</span><strong>{position.symbol}</strong></div></td><td className="mono">{position.quantity.toFixed(2)}</td><td className="mono"><Money value={position.market_value}/></td><td className="mono">${position.avg_entry_price.toFixed(2)}</td><td className="mono"><strong>${position.current_price.toFixed(2)}</strong></td><td><div className="weight-cell"><span><i style={{width:`${position.weight*1000}%`}}/></span><strong>{(position.weight*100).toFixed(1)}%</strong></div></td><td><strong className="positive-text">+${position.unrealized_pl.toFixed(2)}</strong><div className="small positive-text">+{(position.unrealized_pl_pct*100).toFixed(2)}%</div></td><td><MiniSparkline values={[2,3+index,2.8,4.4,5.1,4.9,7.2]}/></td></tr>)}</tbody></table></div>
    </Panel>
  </>;
}
