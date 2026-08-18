"use client";

import type { Bar, Position } from "@/lib/types";

export function EquityChart({ bars }: { bars: Bar[] }) {
  const values = bars.map((bar) => bar.close);
  const width = 760;
  const height = 220;
  const min = Math.min(...values) * 0.995;
  const max = Math.max(...values) * 1.005;
  const points = values.map((value, index) => `${(index / Math.max(values.length - 1, 1)) * width},${height - ((value - min) / (max - min || 1)) * height}`).join(" ");
  const area = `M0,${height} L${points.replaceAll(" ", " L")} L${width},${height} Z`;
  return <div className="chart-wrap"><div className="chart-grid"><span/><span/><span/><span/></div><svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="Portfolio equity curve"><defs><linearGradient id="area-green" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#27e5a3" stopOpacity=".24"/><stop offset="100%" stopColor="#27e5a3" stopOpacity="0"/></linearGradient></defs><path d={area} fill="url(#area-green)"/><polyline points={points} fill="none" stroke="#30e6a6" strokeWidth="2.4" vectorEffect="non-scaling-stroke"/><circle cx={width} cy={Number(points.split(" ").at(-1)?.split(",")[1])} r="4" fill="#30e6a6" vectorEffect="non-scaling-stroke"/></svg><div className="chart-axis"><span>JUL 01</span><span>JUL 15</span><span>AUG 01</span><span>AUG 12</span></div></div>;
}

export function MiniSparkline({ values, tone = "good" }: { values: number[]; tone?: "good" | "bad" | "warn" }) {
  const width = 100, height = 34, min = Math.min(...values), max = Math.max(...values);
  const points = values.map((value, index) => `${(index / Math.max(values.length - 1, 1)) * width},${height - ((value - min) / (max - min || 1)) * height}`).join(" ");
  return <svg className={`sparkline ${tone}`} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none"><polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke"/></svg>;
}

export function AllocationDonut({ positions }: { positions: Position[] }) {
  const colors = ["#2ee6a6", "#7a8cff", "#e9b75e", "#6dd5ed"];
  let offset = 0;
  const invested = positions.reduce((sum, item) => sum + item.weight, 0);
  const segments = [...positions.map((position, index) => ({ label: position.symbol, value: position.weight, color: colors[index % colors.length] })), { label: "Cash", value: Math.max(0, 1 - invested), color: "#1f302d" }];
  return <div className="allocation"><div className="donut"><svg viewBox="0 0 42 42">{segments.map((segment) => { const dash = segment.value * 100; const item = <circle key={segment.label} cx="21" cy="21" r="15.9" fill="none" stroke={segment.color} strokeWidth="5" strokeDasharray={`${dash} ${100 - dash}`} strokeDashoffset={-offset} />; offset += dash; return item; })}</svg><div><strong>{Math.round(invested * 100)}%</strong><span>invested</span></div></div><div className="allocation-legend">{segments.map((segment) => <div key={segment.label}><span style={{ backgroundColor: segment.color }}/><strong>{segment.label}</strong><em>{Math.round(segment.value * 100)}%</em></div>)}</div></div>;
}
