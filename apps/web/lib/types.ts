export type Action = "BUY" | "SELL" | "HOLD";
export type RiskDecision = "APPROVE" | "MODIFY" | "REJECT" | "ESCALATE";
export type Severity = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface EvidenceItem {
  label: string;
  value: string;
  source: string;
  importance: number;
}

export interface AgentDecision {
  agent_name: "market" | "news" | "quant" | "portfolio";
  display_name: string;
  symbol: string;
  action: Action;
  confidence: number;
  thesis: string;
  evidence: EvidenceItem[];
  bullish_factors: string[];
  bearish_factors: string[];
  risk_flags: string[];
  suggested_position_pct: number;
  invalidation_conditions: string[];
  engine: string;
  latency_ms: number;
}

export interface Consensus {
  direction: Action;
  confidence: number;
  weighted_score: number;
  agreement_ratio: number;
  disagreement_score: number;
  agreeing_agents: number;
  total_agents: number;
  supporting_agents: string[];
  dissenting_agents: string[];
}

export interface RiskCheck {
  rule_id: string;
  rule_name: string;
  passed: boolean;
  severity: Severity;
  message: string;
}

export interface RiskGate {
  decision: RiskDecision;
  requested_position_pct: number;
  approved_position_pct: number;
  checks: RiskCheck[];
  reasons: string[];
}

export interface Position {
  symbol: string;
  quantity: number;
  market_value: number;
  avg_entry_price: number;
  current_price: number;
  unrealized_pl: number;
  unrealized_pl_pct: number;
  weight: number;
}

export interface Account {
  account_id: string;
  status: string;
  equity: number;
  cash: number;
  buying_power: number;
  options_buying_power?: number;
  options_approved_level?: number;
  options_trading_level?: number;
  day_pl: number;
  day_pl_pct: number;
  portfolio_drawdown_pct: number;
  trades_today: number;
  positions: Position[];
  source: "DEMO_REPLAY" | "ALPACA_PAPER";
}

export interface Bar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface SocAlert {
  id: string;
  rule_id: string;
  alert_type: string;
  severity: Severity;
  title: string;
  detail: string;
  symbol?: string;
  workflow_run_id?: string;
  status: "OPEN" | "ACKNOWLEDGED" | "RESOLVED";
  created_at: string;
}

export interface TimelineEvent {
  id: string;
  event: string;
  title: string;
  detail: string;
  status: "COMPLETE" | "WARNING" | "BLOCKED" | "PENDING";
  timestamp: string;
}

export interface Order {
  id: string;
  provider_order_id: string;
  client_order_id: string;
  workflow_run_id: string;
  symbol: string;
  side: "BUY" | "SELL";
  notional: number;
  status: string;
  execution_mode: "SIMULATED_PAPER" | "ALPACA_PAPER";
  submitted_at: string;
  risk_decision: RiskDecision;
  quantity?: number;
  instrument_type: "EQUITY" | "OPTION";
  underlying_symbol?: string;
  order_type: "market" | "limit";
  limit_price?: number;
  position_intent?: "BUY_TO_OPEN" | "SELL_TO_CLOSE";
  execution_interface: "ALPACA_SDK" | "ALPACA_CLI" | "SIMULATED_REPLAY";
}

export interface OptionContract {
  symbol: string;
  underlying_symbol: string;
  option_type: "PUT" | "CALL";
  expiration_date: string;
  strike_price: number;
  multiplier: number;
  tradable: boolean;
  open_interest?: number;
  bid_price: number;
  ask_price: number;
  mid_price: number;
  quote_as_of: string;
  source: "DEMO_REPLAY" | "ALPACA_PAPER";
}

export interface HedgePlan {
  action: "OPEN" | "HOLD" | "RELEASE";
  strategy: "PROTECTIVE_PUT";
  underlying_symbol: string;
  underlying_quantity: number;
  underlying_market_value: number;
  risk: {
    score: number;
    level: "LOW" | "ELEVATED" | "HIGH" | "CRITICAL";
    components: Record<string, number>;
    reasons: string[];
  };
  target_hedge_ratio: number;
  actual_hedge_ratio: number;
  contract?: OptionContract;
  contracts: number;
  covered_shares: number;
  limit_price?: number;
  estimated_premium: number;
  premium_pct_equity: number;
  rationale: string[];
  release_conditions: string[];
  rebalance_conditions: string[];
  execution_interface: "SIMULATED_REPLAY" | "ALPACA_CLI";
}

export interface Workflow {
  workflow_run_id: string;
  symbol: string;
  status: string;
  mode: "REPLAY" | "LIVE";
  scenario: string;
  agent_provider: "RULES" | "OPENAI";
  strategy: "EQUITY" | "PROTECTIVE_PUT";
  replay_of?: string;
  created_at: string;
  completed_at?: string;
  market_snapshot: {
    symbol: string;
    price: number;
    change_pct: number;
    as_of: string;
    source: "DEMO_REPLAY" | "ALPACA_PAPER";
    bars: Bar[];
    indicators: Record<string, number>;
  };
  news_items: Array<Record<string, unknown>>;
  account: Account;
  agent_decisions: AgentDecision[];
  consensus: Consensus;
  risk_review: {
    verdict: "SUPPORT" | "CAUTION" | "REJECT_RECOMMENDATION";
    semantic_risk_score: number;
    issues: string[];
    explanation: string;
    engine: string;
  };
  proposal?: {
    requested_position_pct: number;
    requested_notional?: number;
    side: "BUY" | "SELL";
    thesis: string;
    instrument_type?: "EQUITY" | "OPTION";
    underlying_symbol?: string;
    position_intent?: "BUY_TO_OPEN" | "SELL_TO_CLOSE";
  };
  hedge_plan?: HedgePlan;
  risk_gate: RiskGate;
  execution?: Order;
  explanation: {
    headline: string;
    summary: string;
    final_action: Action;
    confidence: number;
    positive_factors: string[];
    negative_factors: string[];
    agent_votes: Array<Record<string, unknown>>;
    consensus_explanation: string;
    risk_decision: RiskDecision;
    triggered_rules: RiskCheck[];
    requested_size: number;
    approved_size: number;
    invalidation_conditions: string[];
    execution_status?: string;
  };
  soc_alerts: SocAlert[];
  timeline: TimelineEvent[];
  errors: string[];
}

export interface RiskPolicy {
  key: string;
  label: string;
  value: number | boolean;
  unit: "percent" | "count" | "seconds" | "boolean";
  locked: boolean;
  description: string;
}
