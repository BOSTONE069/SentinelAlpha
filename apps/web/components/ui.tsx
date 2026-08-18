import Link from "next/link";
import type { Action, RiskDecision, Severity } from "@/lib/types";
import { Icon, type IconName } from "./icons";

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description: string; actions?: React.ReactNode }) {
  return <div className="page-header"><div>{eyebrow && <div className="eyebrow">{eyebrow}</div>}<h1>{title}</h1><p>{description}</p></div>{actions && <div className="page-actions">{actions}</div>}</div>;
}

export function StatusPill({ value, subtle = false }: { value: Action | RiskDecision | Severity | string; subtle?: boolean }) {
  const tone = ["BUY", "APPROVE", "SUPPORT", "LOW", "HEALTHY", "PASSED", "COMPLETE", "filled"].includes(value) ? "good" : ["SELL", "REJECT", "CRITICAL", "HIGH", "FAILED", "REJECTED", "BLOCKED"].includes(value) ? "bad" : ["MODIFY", "ESCALATE", "MEDIUM", "CAUTION", "AWAITING_APPROVAL", "WARNING"].includes(value) ? "warn" : "neutral";
  return <span className={`status-pill ${tone} ${subtle ? "subtle" : ""}`}><span />{value.replaceAll("_", " ")}</span>;
}

export function MetricCard({ label, value, delta, icon, tone = "default", footer }: { label: string; value: string; delta?: string; icon?: IconName; tone?: "default" | "good" | "warn" | "bad"; footer?: string }) {
  return <div className={`metric-card tone-${tone}`}><div className="metric-top"><span>{label}</span>{icon && <span className="metric-icon"><Icon name={icon} /></span>}</div><div className="metric-value">{value}</div>{(delta || footer) && <div className="metric-footer">{delta && <span className={delta.startsWith("+") ? "positive-text" : ""}>{delta}</span>}{footer && <span>{footer}</span>}</div>}</div>;
}

export function Panel({ title, kicker, action, className = "", children }: { title?: string; kicker?: string; action?: React.ReactNode; className?: string; children: React.ReactNode }) {
  return <section className={`panel ${className}`}>{(title || kicker || action) && <div className="panel-header"><div>{kicker && <div className="panel-kicker">{kicker}</div>}{title && <h2>{title}</h2>}</div>{action}</div>}<div className="panel-body">{children}</div></section>;
}

export function EmptyState({ icon = "audit", title, detail }: { icon?: IconName; title: string; detail: string }) {
  return <div className="empty-state"><span><Icon name={icon} size={25} /></span><h3>{title}</h3><p>{detail}</p></div>;
}

export function ViewLink({ href, label = "View details" }: { href: string; label?: string }) {
  return <Link href={href} className="view-link">{label}<Icon name="arrow" size={15} /></Link>;
}

export function ProgressRing({ value, size = 98, label }: { value: number; size?: number; label?: string }) {
  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  return <div className="progress-ring" style={{ width: size, height: size }}><svg viewBox="0 0 90 90"><circle className="ring-track" cx="45" cy="45" r={radius}/><circle className="ring-value" cx="45" cy="45" r={radius} strokeDasharray={circumference} strokeDashoffset={circumference * (1 - value)} /></svg><div><strong>{Math.round(value * 100)}%</strong>{label && <span>{label}</span>}</div></div>;
}

export function Money({ value }: { value: number }) {
  return <>{new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value)}</>;
}
