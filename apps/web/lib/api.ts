import { demoAccount, demoAlerts, demoOrders, demoPolicies, demoRuns, makeDemoHedgeRun, makeDemoRun } from "./demo";
import type { Account, Order, RiskPolicy, SocAlert, Workflow } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const TOKEN_KEY = "sentinelalpha.api-auth-token";

export type AuthenticatedActor = {
  user_id: string;
  portfolio_ids: string[];
  role: "viewer" | "operator" | "admin";
  can_write: boolean;
};

function authToken(): string | null {
  return typeof window === "undefined" ? null : window.sessionStorage.getItem(TOKEN_KEY);
}

function authenticatedHeaders(): HeadersInit {
  const token = authToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authenticatedHeaders(),
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail ?? `Request failed with ${response.status}`);
  }
  return response.json() as Promise<T>;
}

async function downloadAudit(runId?: string): Promise<void> {
  const query = runId ? `?run_id=${encodeURIComponent(runId)}` : "";
  const response = await fetch(`${API_URL}/audit/export${query}`, {
    cache: "no-store",
    headers: authenticatedHeaders(),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    const detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    throw new Error(detail || `Export failed with ${response.status}`);
  }

  const disposition = response.headers.get("Content-Disposition") ?? "";
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1]
    ?? `sentinelalpha-audit-${new Date().toISOString().replaceAll(":", "-")}.json`;
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

export const api = {
  health: () => request<Record<string, unknown>>("/health").catch(() => ({ status: "offline-demo", paper_trading: true, live_trading_enabled: false })),
  authMe: () => request<AuthenticatedActor>("/auth/me"),
  authenticate: async (token: string) => {
    window.sessionStorage.setItem(TOKEN_KEY, token.trim());
    try {
      const actor = await request<AuthenticatedActor>("/auth/me");
      window.dispatchEvent(new Event("sentinelalpha-auth-changed"));
      return actor;
    } catch (error) {
      window.sessionStorage.removeItem(TOKEN_KEY);
      window.dispatchEvent(new Event("sentinelalpha-auth-changed"));
      throw error;
    }
  },
  clearAuthentication: () => {
    window.sessionStorage.removeItem(TOKEN_KEY);
    window.dispatchEvent(new Event("sentinelalpha-auth-changed"));
  },
  hasAuthentication: () => Boolean(authToken()),
  account: () => request<Account>("/alpaca/account?mode=REPLAY").catch(() => demoAccount),
  runs: () => request<Workflow[]>("/runs").then((items) => items.length ? items : demoRuns).catch(() => demoRuns),
  run: (id: string) => request<Workflow>(`/runs/${id}`).catch(() => demoRuns.find((run) => run.workflow_run_id === id) ?? (id.includes("portfolio-protection") ? makeDemoHedgeRun("NVDA") : makeDemoRun("AAPL"))),
  analyze: async (symbol: string, scenario: string, agentProvider: "RULES" | "OPENAI", mode: "REPLAY" | "LIVE") => {
    try {
      const response = await request<{ result: Workflow }>("/analysis", { method: "POST", body: JSON.stringify({ symbol, scenario, agent_provider: agentProvider, mode, auto_execute: false }) });
      return response.result;
    } catch (error) {
      if (mode === "LIVE" || agentProvider === "OPENAI") throw error;
      return makeDemoRun(symbol, scenario);
    }
  },
  analyzeHedge: async (symbol: string, agentProvider: "RULES" | "OPENAI", mode: "REPLAY" | "LIVE", autoExecute = false) => {
    try {
      const response = await request<{ result: Workflow }>("/analysis", { method: "POST", body: JSON.stringify({ symbol, scenario: "portfolio_protection", strategy: "PROTECTIVE_PUT", agent_provider: agentProvider, mode, auto_execute: autoExecute }) });
      return response.result;
    } catch (error) {
      if (mode === "LIVE" || agentProvider === "OPENAI") throw error;
      return makeDemoHedgeRun(symbol);
    }
  },
  approve: (id: string) => request<Workflow>(`/runs/${id}/approve`, { method: "POST" }),
  reject: (id: string) => request<Workflow>(`/runs/${id}/reject`, { method: "POST" }),
  replay: (id: string) => request<Workflow>(`/runs/${id}/replay`, { method: "POST" }),
  alerts: () => request<SocAlert[]>("/soc/alerts").then((items) => items.length ? items : demoAlerts).catch(() => demoAlerts),
  socOverview: () => request<{ system_risk_score: number; system_status: string; agent_health: { healthy: number; total: number }; active_alerts: number; trades_blocked_today: number; kill_switch: boolean }>("/soc/overview").catch(() => ({ system_risk_score: 18, system_status: "LOW", agent_health: { healthy: 5, total: 5 }, active_alerts: 3, trades_blocked_today: 4, kill_switch: false })),
  policies: () => request<RiskPolicy[]>("/risk/policies").catch(() => demoPolicies),
  updatePolicy: (key: string, value: number | boolean) => request<RiskPolicy>(`/risk/policies/${key}`, { method: "PUT", body: JSON.stringify({ value }) }),
  riskStatus: () => request<{ kill_switch: boolean; executions_enabled: boolean }>("/risk/status").catch(() => ({ kill_switch: false, executions_enabled: true })),
  setKillSwitch: (engaged: boolean) => request<{ kill_switch: boolean }>(engaged ? "/risk/kill-switch" : "/risk/kill-switch/reset", { method: "POST" }),
  orders: () => request<Order[]>("/orders").then((items) => items.length ? items : demoOrders).catch(() => demoOrders),
  exportAudit: (runId?: string) => downloadAudit(runId),
};
