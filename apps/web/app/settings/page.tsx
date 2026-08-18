"use client";

import { useEffect, useState } from "react";
import { PageHeader, Panel, StatusPill } from "@/components/ui";
import { api, type AuthenticatedActor } from "@/lib/api";

export default function SettingsPage() {
  const [token,setToken] = useState("");
  const [actor,setActor] = useState<AuthenticatedActor | null>(null);
  const [checking,setChecking] = useState(false);
  const [error,setError] = useState("");

  useEffect(()=>{
    if (api.hasAuthentication()) {
      api.authMe().then(setActor).catch(()=>api.clearAuthentication());
    }
  },[]);

  async function connect() {
    if (!token.trim()) return;
    setChecking(true);
    setError("");
    try {
      const authenticated = await api.authenticate(token);
      setActor(authenticated);
      setToken("");
    } catch (nextError) {
      setActor(null);
      setError(nextError instanceof Error ? nextError.message : "Authentication failed.");
    } finally {
      setChecking(false);
    }
  }

  function disconnect() {
    api.clearAuthentication();
    setActor(null);
    setToken("");
  }

  return <><PageHeader eyebrow="Environment configuration" title="System settings" description="Provider credentials stay server-side. This screen exposes connection posture without exposing any secret material."/>
    <Panel title="Dashboard authentication" kicker="Bearer token · session-only storage" className="spaced-panel"><div className="auth-settings"><div><span>Session</span><StatusPill value={actor ? "AUTHENTICATED" : "AUTH REQUIRED"}/></div>{actor && <div><span>Role</span><strong className="mono">{actor.role.toUpperCase()}</strong></div>}<p>The operator token is kept only in this browser tab and sent to the API in the Authorization header. It is never bundled into the frontend.</p><div className="auth-token-row"><input type="password" value={token} onChange={(event)=>setToken(event.target.value)} onKeyDown={(event)=>{if(event.key==="Enter") void connect();}} autoComplete="current-password" placeholder="Paste API_AUTH_TOKEN" aria-label="API authentication token"/>{actor ? <button className="button ghost" type="button" onClick={disconnect}>Disconnect</button> : <button className="button primary" type="button" onClick={connect} disabled={checking||!token.trim()}>{checking?"Checking…":"Authenticate"}</button>}</div>{error&&<div className="error-banner" role="alert"><div><strong>Authentication failed</strong><span>{error}</span></div></div>}</div></Panel>
    <div className="grid-2"><Panel title="Alpaca paper trading" kicker="Broker connection"><div className="settings-list"><div><span>Environment</span><StatusPill value="PAPER"/></div><div><span>Option execution</span><StatusPill value="ALPACA CLI"/></div><div><span>Options data</span><StatusPill value="INDICATIVE"/></div><div><span>Execution approval</span><StatusPill value="HUMAN REQUIRED"/></div><div><span>Live-money endpoint</span><StatusPill value="DISABLED"/></div></div></Panel><Panel title="Agent provider" kicker="Structured reasoning"><div className="settings-list"><div><span>Stable replay engine</span><StatusPill value="AVAILABLE"/></div><div><span>OpenAI structured outputs</span><StatusPill value="OPTIONAL"/></div><div><span>News prompt isolation</span><StatusPill value="ACTIVE"/></div><div><span>Order tools for models</span><StatusPill value="DENIED"/></div></div></Panel></div>
    <Panel title="Local environment variables" kicker="Configure in .env · provider secrets stay server-side" className="spaced-panel"><div className="env-grid">{["API_AUTH_TOKEN","API_AUTH_ROLE=operator","ALPACA_API_KEY","ALPACA_SECRET_KEY","ALPACA_PAPER=true","ALPACA_DATA_FEED=iex","ALPACA_OPTIONS_FEED=indicative","ALPACA_OPTIONS_EXECUTION_ADAPTER=cli","ALPACA_CLI_PATH=alpaca","OPENAI_API_KEY","OPENAI_MODEL=gpt-5.6","LIVE_TRADING_ENABLED=false","AUTO_EXECUTE_PAPER=false","DATABASE_URL","REDIS_URL","REDIS_REQUIRED=false"].map((item)=><code key={item}>{item}</code>)}</div></Panel>
  </>;
}
