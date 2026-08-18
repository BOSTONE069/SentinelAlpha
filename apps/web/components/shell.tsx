"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Icon, type IconName } from "./icons";

const navigation: Array<{ href: string; label: string; icon: IconName }> = [
  { href: "/", label: "Overview", icon: "grid" },
  { href: "/council", label: "Agent Council", icon: "council" },
  { href: "/hedging", label: "Hedge Agent", icon: "shield" },
  { href: "/portfolio", label: "Portfolio", icon: "briefcase" },
  { href: "/soc", label: "Trading SOC", icon: "shield" },
  { href: "/decisions", label: "Decisions", icon: "decision" },
  { href: "/orders", label: "Orders", icon: "order" },
  { href: "/risk", label: "Risk Policies", icon: "policy" },
  { href: "/audit", label: "Audit", icon: "audit" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="sidebar">
      <Link href="/" className="brand" aria-label="SentinelAlpha home">
        <span className="brand-mark"><span /></span>
        <span><strong>Sentinel</strong>Alpha</span>
      </Link>
      <div className="sidebar-label">Control plane</div>
      <nav className="nav-list">
        {navigation.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return <Link key={item.href} href={item.href} className={`nav-link ${active ? "active" : ""}`}><Icon name={item.icon} /><span>{item.label}</span>{active && <span className="active-dot" />}</Link>;
        })}
      </nav>
      <div className="sidebar-bottom">
        <div className="boundary-card">
          <div className="boundary-icon"><Icon name="lock" size={15} /></div>
          <div><span>Execution boundary</span><strong>Paper mode locked</strong></div>
          <span className="online-dot" />
        </div>
        <Link href="/settings" className={`nav-link ${pathname.startsWith("/settings") ? "active" : ""}`}><Icon name="settings" /><span>Settings</span></Link>
        <div className="operator">
          <div className="avatar">SA</div>
          <div><strong>Demo Operator</strong><span>Risk reviewer</span></div>
          <span className="kebab">•••</span>
        </div>
      </div>
    </aside>
  );
}

export function Topbar() {
  const [authenticated, setAuthenticated] = useState(false);
  useEffect(() => {
    const checkAuthentication = () => {
      if (!api.hasAuthentication()) {
        setAuthenticated(false);
        return;
      }
      api.authMe().then(()=>setAuthenticated(true)).catch(()=>setAuthenticated(false));
    };
    checkAuthentication();
    window.addEventListener("sentinelalpha-auth-changed", checkAuthentication);
    return () => window.removeEventListener("sentinelalpha-auth-changed", checkAuthentication);
  }, []);
  return (
    <header className="topbar">
      <div className="environment"><span className="status-dot positive" />PAPER ENVIRONMENT<span className="separator" /><span className="market-state">MARKET OPEN</span></div>
      <div className="top-actions">
        <span className={`api-state ${authenticated ? "online" : "demo"}`}><span />{authenticated ? "AUTHENTICATED" : "AUTH REQUIRED"}</span>
        <button className="icon-button" aria-label="Search"><Icon name="search" /></button>
        <button className="icon-button notification" aria-label="Notifications"><Icon name="bell" /><span /></button>
      </div>
    </header>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  return <div className="app-shell"><Sidebar /><div className="workspace"><Topbar /><main className="page-shell">{children}</main></div></div>;
}
