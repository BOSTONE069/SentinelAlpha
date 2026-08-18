import type { Account, AgentDecision, Bar, Order, RiskPolicy, SocAlert, Workflow } from "./types";

const now = new Date();

export const demoAccount: Account = {
  account_id: "paper-demo-01",
  status: "ACTIVE",
  equity: 100000,
  cash: 63420,
  buying_power: 126840,
  day_pl: 842.18,
  day_pl_pct: 0.0085,
  portfolio_drawdown_pct: 0.012,
  trades_today: 3,
  source: "DEMO_REPLAY",
  positions: [
    { symbol: "NVDA", quantity: 43.67, market_value: 8000, avg_entry_price: 168.4, current_price: 183.2, unrealized_pl: 646.32, unrealized_pl_pct: 0.0879, weight: 0.08 },
    { symbol: "AAPL", quantity: 26.27, market_value: 6000, avg_entry_price: 211.8, current_price: 228.4, unrealized_pl: 436.7, unrealized_pl_pct: 0.0785, weight: 0.06 },
    { symbol: "MSFT", quantity: 11.49, market_value: 6000, avg_entry_price: 487.3, current_price: 522.1, unrealized_pl: 399.85, unrealized_pl_pct: 0.0714, weight: 0.06 },
  ],
};

const bars: Bar[] = Array.from({ length: 44 }, (_, index) => {
  const close = 202 + index * 0.58 + Math.sin(index / 2.8) * 2.1;
  return {
    timestamp: new Date(now.getTime() - (43 - index) * 86400000).toISOString(),
    open: close - 0.7,
    high: close + 1.5,
    low: close - 1.8,
    close,
    volume: 42000000 + Math.round(Math.sin(index) * 5000000),
  };
});

const decisions: AgentDecision[] = [
  { agent_name: "market", display_name: "Market Intelligence", symbol: "AAPL", action: "BUY", confidence: 0.84, thesis: "Trend, momentum, and participation align to the upside.", evidence: [{ label: "SMA structure", value: "223.18 / 216.42", source: "computed", importance: 0.92 }], bullish_factors: ["Price is above both SMA20 and SMA50", "Relative volume is elevated"], bearish_factors: ["RSI indicates an extended move"], risk_flags: [], suggested_position_pct: 0.07, invalidation_conditions: ["Price closes below SMA20"], engine: "rules-v1", latency_ms: 182 },
  { agent_name: "news", display_name: "News Intelligence", symbol: "AAPL", action: "BUY", confidence: 0.76, thesis: "Multiple relevant sources support a positive demand narrative.", evidence: [{ label: "Weighted sentiment", value: "+0.48", source: "supplied news", importance: 0.82 }], bullish_factors: ["Three relevant articles carry positive sentiment"], bearish_factors: ["One source flags valuation risk"], risk_flags: [], suggested_position_pct: 0.06, invalidation_conditions: ["A material negative filing appears"], engine: "rules-v1", latency_ms: 246 },
  { agent_name: "quant", display_name: "Quant Strategy", symbol: "AAPL", action: "BUY", confidence: 0.81, thesis: "Trend and momentum factors produce a positive composite signal.", evidence: [{ label: "MACD / signal", value: "2.43 / 1.96", source: "computed", importance: 0.91 }], bullish_factors: ["Close > SMA20 > SMA50", "MACD is above its signal"], bearish_factors: ["Momentum is approaching an extended regime"], risk_flags: [], suggested_position_pct: 0.075, invalidation_conditions: ["MACD crosses below its signal line"], engine: "rules-v1", latency_ms: 94 },
  { agent_name: "portfolio", display_name: "Portfolio Manager", symbol: "AAPL", action: "BUY", confidence: 0.68, thesis: "The idea fits, but existing exposure requires position-aware sizing.", evidence: [{ label: "Existing exposure", value: "6.0%", source: "paper portfolio", importance: 0.94 }], bullish_factors: ["Buying power is ample"], bearish_factors: ["Technology exposure is already elevated"], risk_flags: ["existing_symbol_exposure"], suggested_position_pct: 0.08, invalidation_conditions: ["Symbol exposure reaches the hard cap"], engine: "rules-v1", latency_ms: 137 },
];

export const demoAlerts: SocAlert[] = [
  { id: "alert-01", rule_id: "SOC003", alert_type: "POSITION_LIMIT_ATTEMPT", severity: "HIGH", title: "Risk gate reduced proposed exposure", detail: "AAPL requested 8.0%; deterministic policy approved 4.0%.", symbol: "AAPL", workflow_run_id: "demo-risk-01", status: "OPEN", created_at: now.toISOString() },
  { id: "alert-02", rule_id: "SOC006", alert_type: "NEWS_SENTIMENT_ANOMALY", severity: "MEDIUM", title: "News sentiment anomaly", detail: "A sharp narrative shift lacks broad corroboration.", symbol: "NVDA", workflow_run_id: "demo-info-02", status: "OPEN", created_at: new Date(now.getTime() - 18 * 60000).toISOString() },
  { id: "alert-03", rule_id: "SOC007", alert_type: "AGENT_LATENCY_ANOMALY", severity: "LOW", title: "Quant response outside baseline", detail: "Response time reached 1.4× the rolling p95.", symbol: "MSFT", status: "ACKNOWLEDGED", created_at: new Date(now.getTime() - 43 * 60000).toISOString() },
];

export function makeDemoRun(symbol = "AAPL", scenario = "risk_modification"): Workflow {
  const information = scenario === "information_risk";
  const soc = scenario === "agent_soc";
  const runDecisions = decisions.map((item) => ({ ...item, symbol }));
  if (information) {
    runDecisions[0] = { ...runDecisions[0], confidence: 0.66 };
    runDecisions[1] = { ...runDecisions[1], confidence: 0.91, risk_flags: ["sentiment_spike", "limited_corroboration"] };
    runDecisions[2] = { ...runDecisions[2], action: "HOLD", confidence: 0.55 };
    runDecisions[3] = { ...runDecisions[3], confidence: 0.63, suggested_position_pct: 0.06 };
  }
  const direction = "BUY" as const;
  const gateDecision = soc ? "REJECT" : information ? "ESCALATE" : "MODIFY";
  const requested = soc ? 0.14 : information ? 0.06 : 0.08;
  const approved = gateDecision === "MODIFY" ? 0.04 : 0;
  const runId = `demo-${scenario}-${Date.now()}`;
  const checks = [
    { rule_id: "R001", rule_name: "Paper mode", passed: true, severity: "INFO" as const, message: "Paper-only execution boundary is locked." },
    { rule_id: "R002", rule_name: "Minimum confidence", passed: !soc, severity: "HIGH" as const, message: `${soc ? "56" : "78"}% consensus; minimum 70%.` },
    { rule_id: "R003", rule_name: "Agent agreement", passed: true, severity: "HIGH" as const, message: "3/4 agents agree; minimum 3." },
    { rule_id: "R004", rule_name: "Position limit", passed: information, severity: "HIGH" as const, message: `Requested ${(requested * 100).toFixed(1)}%; permissible addition ${(approved * 100).toFixed(1)}%.` },
    { rule_id: "R006", rule_name: "Data freshness", passed: !soc, severity: "CRITICAL" as const, message: soc ? "Market input age 720s; maximum 120s." : "Market input age 1s; maximum 120s." },
    { rule_id: "R012", rule_name: "Semantic risk review", passed: !information, severity: "HIGH" as const, message: information ? "Uncorroborated narrative requires escalation." : "Risk agent supports the proposal." },
  ];
  const riskAlerts = soc
    ? [...demoAlerts, { id: "alert-soc", rule_id: "SOC008", alert_type: "TOOL_INVOCATION_ANOMALY", severity: "HIGH" as const, title: "Tool invocation burst", detail: "Eight repeated requests occurred inside one workflow.", symbol, workflow_run_id: runId, status: "OPEN" as const, created_at: now.toISOString() }]
    : demoAlerts.slice(0, information ? 2 : 1);
  return {
    workflow_run_id: runId,
    symbol,
    status: gateDecision === "MODIFY" ? "AWAITING_APPROVAL" : gateDecision === "ESCALATE" ? "ESCALATED" : "REJECTED",
    mode: "REPLAY",
    scenario,
    agent_provider: "RULES",
    strategy: "EQUITY",
    created_at: now.toISOString(),
    completed_at: now.toISOString(),
    market_snapshot: { symbol, price: bars.at(-1)?.close ?? 228.4, change_pct: 0.0118, as_of: now.toISOString(), source: "DEMO_REPLAY", bars, indicators: { sma20: 223.18, sma50: 216.42, rsi14: 67.4, macd: 2.43, macd_signal: 1.96, volatility_annualized: 0.286 } },
    news_items: [],
    account: { ...demoAccount, positions: demoAccount.positions.map((p) => p.symbol === "AAPL" ? { ...p, symbol } : p) },
    agent_decisions: runDecisions,
    consensus: { direction, confidence: soc ? 0.558 : information ? 0.728 : 0.782, weighted_score: soc ? 0.446 : information ? 0.473 : 0.782, agreement_ratio: information || soc ? 0.75 : 1, disagreement_score: information || soc ? 0.25 : 0, agreeing_agents: information || soc ? 3 : 4, total_agents: 4, supporting_agents: information || soc ? ["market", "news", "portfolio"] : ["market", "news", "quant", "portfolio"], dissenting_agents: information || soc ? ["quant"] : [] },
    risk_review: { verdict: information ? "REJECT_RECOMMENDATION" : soc ? "CAUTION" : "SUPPORT", semantic_risk_score: information ? 0.86 : soc ? 0.79 : 0.24, issues: information ? ["single_unconfirmed_narrative", "contradictory_narrative"] : [], explanation: information ? "The proposal depends too heavily on one uncorroborated narrative." : "Evidence is consistent; deterministic policy should constrain size.", engine: "rules-v1" },
    proposal: { requested_position_pct: requested, requested_notional: requested * 100000, side: "BUY", thesis: "Constructive trend with supervised sizing." },
    risk_gate: { decision: gateDecision, requested_position_pct: requested, approved_position_pct: approved, checks, reasons: [gateDecision === "MODIFY" ? "Position reduced from 8.0% to 4.0% by deterministic limits." : gateDecision === "ESCALATE" ? "Information quality requires human escalation." : "Confidence and freshness checks failed closed."] },
    explanation: { headline: `${symbol} BUY ${gateDecision === "MODIFY" ? "approved at a policy-reduced size" : "proposal — " + gateDecision.toLowerCase()}`, summary: `The council produced a BUY opinion. The deterministic gate returned ${gateDecision}.`, final_action: "BUY", confidence: soc ? 0.558 : information ? 0.728 : 0.782, positive_factors: ["Price above SMA20 and SMA50", "Positive MACD structure", "Relative volume elevated"], negative_factors: ["Technology exposure already elevated", information ? "Lead narrative lacks corroboration" : "Momentum is approaching an extended regime"], agent_votes: [], consensus_explanation: "Code-weighted votes produced the aggregate score; no model controls the aggregation rule.", risk_decision: gateDecision, triggered_rules: checks.filter((c) => !c.passed || c.rule_id === "R004"), requested_size: requested, approved_size: approved, invalidation_conditions: ["Price closes below SMA20", "Material negative news appears", "Volatility crosses the configured threshold"] },
    soc_alerts: riskAlerts,
    timeline: [
      { id: "evt-1", event: "workflow.started", title: "Agent Council started", detail: `${symbol} entered the supervised replay pipeline.`, status: "COMPLETE", timestamp: new Date(now.getTime() - 4200).toISOString() },
      { id: "evt-2", event: "market.loaded", title: "Market context loaded", detail: "90 bars and 13 indicators normalized.", status: "COMPLETE", timestamp: new Date(now.getTime() - 3400).toISOString() },
      { id: "evt-3", event: "agents.completed", title: "Four independent votes captured", detail: "Agent outputs validated against the shared schema.", status: "COMPLETE", timestamp: new Date(now.getTime() - 1900).toISOString() },
      { id: "evt-4", event: `risk.${gateDecision.toLowerCase()}`, title: `Deterministic gate: ${gateDecision}`, detail: gateDecision === "MODIFY" ? "Requested exposure reduced from 8% to 4%." : "Execution was blocked.", status: gateDecision === "MODIFY" ? "WARNING" : "BLOCKED", timestamp: now.toISOString() },
    ],
    errors: [],
  };
}

export function makeDemoHedgeRun(symbol = "NVDA"): Workflow {
  const base = makeDemoRun(symbol, "risk_modification");
  const price = symbol === "NVDA" ? 183.2 : base.market_snapshot.price;
  const expiration = new Date(Date.now() + 31 * 86400000);
  const expirationCode = `${String(expiration.getUTCFullYear()).slice(-2)}${String(expiration.getUTCMonth() + 1).padStart(2, "0")}${String(expiration.getUTCDate()).padStart(2, "0")}`;
  const strike = Math.round((price * 0.95) / 5) * 5;
  const optionSymbol = `${symbol}${expirationCode}P${String(Math.round(strike * 1000)).padStart(8, "0")}`;
  const quoteTime = new Date().toISOString();
  const hedgePlan = {
    action: "OPEN" as const,
    strategy: "PROTECTIVE_PUT" as const,
    underlying_symbol: symbol,
    underlying_quantity: 100,
    underlying_market_value: price * 100,
    risk: {
      score: 0.65,
      level: "ELEVATED" as const,
      components: { concentration: 0.92, volatility: 0.66, negative_momentum: 0.6, negative_news: 0.59, drawdown: 0.76, council_defensiveness: 1 },
      reasons: [`${symbol} concentration is ${(price / 1000).toFixed(1)}% of portfolio equity`, "20-day momentum has deteriorated", "negative news is independently corroborated", "portfolio drawdown has reached 6.1%"],
    },
    target_hedge_ratio: 0.5,
    actual_hedge_ratio: 1,
    contract: { symbol: optionSymbol, underlying_symbol: symbol, option_type: "PUT" as const, expiration_date: expiration.toISOString().slice(0, 10), strike_price: strike, multiplier: 100, tradable: true, open_interest: 1200, bid_price: 4.03, ask_price: 4.27, mid_price: 4.15, quote_as_of: quoteTime, source: "DEMO_REPLAY" as const },
    contracts: 1,
    covered_shares: 100,
    limit_price: 4.27,
    estimated_premium: 427,
    premium_pct_equity: 0.00427,
    rationale: [`${symbol} concentration is elevated`, "negative momentum and news increase drawdown probability", `buy 1 ${expiration.toISOString().slice(0, 10)} $${strike} put at a $4.27 limit`, "protect 100 of 100 shares"],
    release_conditions: ["Risk score falls below 35%", "Negative event risk passes and sentiment normalizes", "Underlying recovers above its 20-day trend", "Close or roll before seven DTE"],
    rebalance_conditions: ["Underlying share quantity changes by 25%", "Hedge ratio drifts by 20 percentage points", "Volatility regime changes"],
    execution_interface: "SIMULATED_REPLAY" as const,
  };
  const checks = [
    ["H001", "Paper mode", "Alpaca paper execution is locked."],
    ["H002", "Protectable underlying", "Underlying position contains 100 shares."],
    ["H003", "Hedge threshold", "Risk score 65%; activation threshold 55%."],
    ["H004", "Protective-put contract", "Selected contract is an active, tradable put."],
    ["H005", "Expiration window", "Selected contract has 31 DTE; allowed range 21–45."],
    ["H006", "Strike distance", "Put strike is approximately 5% out of the money."],
    ["H007", "Hedge size", "One contract protects 100% of the position."],
    ["H008", "Premium budget", "Estimated premium is 0.43% of equity; cap 2%."],
    ["H009", "Option liquidity", "Relative bid/ask spread is within policy."],
    ["H010", "Quote freshness", "Option quote is current."],
    ["H016", "Hackathon interface", "Execution interface is simulated Alpaca CLI replay."],
    ["H017", "Options account permission", "Approved and active options trading level is 3."],
  ].map(([rule_id, rule_name, message]) => ({ rule_id, rule_name, passed: true, severity: "INFO" as const, message }));
  const agentDecisions = base.agent_decisions.map((decision, index) => ({ ...decision, action: "SELL" as const, confidence: [0.82, 0.79, 0.84, 0.88][index], suggested_position_pct: 0, thesis: ["Trend deterioration and elevated volatility favor defense.", "Corroborated negative news increases downside risk.", "Negative momentum supports a time-bounded hedge.", "Concentration and drawdown justify bounded-cost protection."][index] }));
  return {
    ...base,
    workflow_run_id: `demo-portfolio-protection-${Date.now()}`,
    status: "AWAITING_APPROVAL",
    scenario: "portfolio_protection",
    strategy: "PROTECTIVE_PUT",
    market_snapshot: { ...base.market_snapshot, symbol, price, change_pct: -0.018, as_of: quoteTime },
    account: { ...base.account, options_buying_power: 25000, options_approved_level: 3, options_trading_level: 3, day_pl: -2180, day_pl_pct: -0.0218, portfolio_drawdown_pct: 0.061, positions: [{ symbol, quantity: 100, market_value: price * 100, avg_entry_price: price * 1.08, current_price: price, unrealized_pl: -(price * 100 * 0.074), unrealized_pl_pct: -0.074, weight: price / 1000 }] },
    agent_decisions: agentDecisions,
    consensus: { direction: "SELL", confidence: 0.833, weighted_score: -0.833, agreement_ratio: 1, disagreement_score: 0, agreeing_agents: 4, total_agents: 4, supporting_agents: ["market", "news", "quant", "portfolio"], dissenting_agents: [] },
    risk_review: { verdict: "SUPPORT", semantic_risk_score: 0.41, issues: ["sector_concentration", "drawdown_risk", "hedge_candidate"], explanation: "Corroborated downside evidence and concentrated exposure justify evaluating a bounded-cost protective put.", engine: "rules-v1" },
    hedge_plan: hedgePlan,
    proposal: { requested_position_pct: 0.00427, requested_notional: 427, side: "BUY", thesis: hedgePlan.rationale.join("; "), instrument_type: "OPTION", underlying_symbol: symbol, position_intent: "BUY_TO_OPEN" },
    risk_gate: { decision: "APPROVE", requested_position_pct: 0.00427, approved_position_pct: 0.00427, checks, reasons: ["Protective put approved: 1 contract, 100% coverage, $427 maximum premium."] },
    explanation: { ...base.explanation, headline: `${symbol} protective put — approved`, summary: `SentinelAlpha measured elevated portfolio risk and proposed one protective put covering 100 shares for at most $427.`, final_action: "BUY", confidence: 0.65, positive_factors: hedgePlan.rationale, negative_factors: ["Option premium creates carry cost", "Protection can expire without intrinsic value"], risk_decision: "APPROVE", triggered_rules: checks.filter((check) => ["H003", "H007", "H008", "H016"].includes(check.rule_id)), requested_size: 0.00427, approved_size: 0.00427, invalidation_conditions: hedgePlan.release_conditions },
    timeline: [...base.timeline, { id: "evt-options", event: "options.loaded", title: "Protective-put universe loaded", detail: "Six replay contracts normalized.", status: "COMPLETE", timestamp: quoteTime }, { id: "evt-hedge", event: "hedge_agent.completed", title: "Hedge Agent returned OPEN", detail: `Selected ${optionSymbol}.`, status: "COMPLETE", timestamp: quoteTime }],
  };
}

export const demoOrders: Order[] = [
  { id: "ord-21f8", provider_order_id: "sim-paper-21f8c91a", client_order_id: "sa-demo-aapl-buy", workflow_run_id: "demo-risk-01", symbol: "AAPL", side: "BUY", notional: 4000, status: "filled", execution_mode: "SIMULATED_PAPER", submitted_at: new Date(now.getTime() - 38 * 60000).toISOString(), risk_decision: "MODIFY", instrument_type: "EQUITY", order_type: "market", execution_interface: "SIMULATED_REPLAY" },
  { id: "ord-9e42", provider_order_id: "sim-paper-9e42d130", client_order_id: "sa-demo-msft-buy", workflow_run_id: "demo-risk-04", symbol: "MSFT", side: "BUY", notional: 2800, status: "filled", execution_mode: "SIMULATED_PAPER", submitted_at: new Date(now.getTime() - 164 * 60000).toISOString(), risk_decision: "APPROVE", instrument_type: "EQUITY", order_type: "market", execution_interface: "SIMULATED_REPLAY" },
];

export const demoPolicies: RiskPolicy[] = [
  { key: "max_single_position_pct", label: "Maximum single position", value: 0.1, unit: "percent", locked: false, description: "Hard cap for total symbol exposure." },
  { key: "max_new_position_pct", label: "Maximum new position", value: 0.05, unit: "percent", locked: false, description: "Maximum exposure added by one workflow." },
  { key: "max_daily_loss_pct", label: "Daily loss limit", value: 0.03, unit: "percent", locked: false, description: "Blocks new risk after this daily loss." },
  { key: "max_portfolio_drawdown_pct", label: "Portfolio drawdown limit", value: 0.08, unit: "percent", locked: false, description: "Activates the execution kill switch." },
  { key: "min_consensus_confidence", label: "Minimum consensus", value: 0.7, unit: "percent", locked: false, description: "Required code-derived council confidence." },
  { key: "min_agreeing_agents", label: "Minimum agreeing agents", value: 3, unit: "count", locked: false, description: "Minimum matching analytical votes." },
  { key: "max_trades_per_day", label: "Trades per day", value: 10, unit: "count", locked: false, description: "Daily execution ceiling." },
  { key: "max_data_age_seconds", label: "Maximum data age", value: 120, unit: "seconds", locked: false, description: "Rejects stale market inputs." },
  { key: "allow_shorting", label: "Allow shorting", value: false, unit: "boolean", locked: false, description: "Short exposure is disabled for the MVP." },
  { key: "allow_extended_hours", label: "Allow extended hours", value: false, unit: "boolean", locked: false, description: "Regular market hours only." },
  { key: "hedge_min_risk_score", label: "Minimum hedge risk", value: 0.55, unit: "percent", locked: false, description: "Risk score required before opening protection." },
  { key: "hedge_release_risk_score", label: "Hedge release risk", value: 0.35, unit: "percent", locked: false, description: "Risk score below which protection may be released." },
  { key: "hedge_target_dte", label: "Target option DTE", value: 30, unit: "count", locked: false, description: "Preferred days to expiration." },
  { key: "hedge_min_dte", label: "Minimum option DTE", value: 21, unit: "count", locked: false, description: "Rejects contracts too close to expiration." },
  { key: "hedge_max_dte", label: "Maximum option DTE", value: 45, unit: "count", locked: false, description: "Rejects contracts beyond the hedge horizon." },
  { key: "hedge_target_otm_pct", label: "Target put OTM", value: 0.05, unit: "percent", locked: false, description: "Preferred strike below spot." },
  { key: "hedge_max_otm_pct", label: "Maximum put OTM", value: 0.1, unit: "percent", locked: false, description: "Rejects distant strikes." },
  { key: "hedge_max_ratio", label: "Maximum hedge ratio", value: 1, unit: "percent", locked: false, description: "Caps protected shares relative to the position." },
  { key: "hedge_max_premium_pct", label: "Maximum premium budget", value: 0.02, unit: "percent", locked: false, description: "Caps premium as a share of equity." },
  { key: "hedge_max_spread_pct", label: "Maximum option spread", value: 0.25, unit: "percent", locked: false, description: "Rejects illiquid option quotes." },
  { key: "hedge_max_contracts", label: "Maximum hedge contracts", value: 10, unit: "count", locked: false, description: "Caps contracts opened by one workflow." },
  { key: "paper_mode", label: "Paper mode", value: true, unit: "boolean", locked: true, description: "Execution environment is permanently locked to paper." },
];

export const demoRuns = [makeDemoHedgeRun("NVDA"), makeDemoRun("AAPL"), makeDemoRun("NVDA", "information_risk"), makeDemoRun("TSLA", "agent_soc")];
