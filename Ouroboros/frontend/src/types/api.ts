export type SchemaVersion = "v1";

export type SessionStatus =
  | "created"
  | "running"
  | "paused"
  | "completed"
  | "failed";

export type TickState =
  | "CHRONOS_SEED"
  | "PAYLOAD_SPLIT"
  | "AGENT_STEP"
  | "MATCH_AND_CLEAR"
  | "COMMIT_TICK"
  | "FAILED";

export type ApiErrorCode =
  | "BAD_REQUEST"
  | "UNAUTHORIZED"
  | "FORBIDDEN"
  | "SESSION_NOT_FOUND"
  | "SESSION_STATE_CONFLICT"
  | "SCHEMA_VERSION_UNSUPPORTED"
  | "RATE_LIMITED"
  | "ORCHESTRATOR_BUSY"
  | "SNAPSHOT_REQUIRED"
  | "WS_BACKPRESSURE"
  | "INTERNAL_ERROR";

export interface ApiErrorBody {
  code: ApiErrorCode;
  message: string;
  retryable: boolean;
  details?: Record<string, unknown>;
}

export interface ApiSuccessEnvelope<TData> {
  schema_version: SchemaVersion;
  request_id: string;
  session_id?: string;
  trace_id: string;
  server_time: string;
  data: TData;
}

export interface ApiErrorEnvelope {
  schema_version: SchemaVersion;
  request_id: string;
  session_id?: string;
  trace_id?: string;
  server_time?: string;
  error: ApiErrorBody;
}

export type ApiEnvelope<TData> = ApiSuccessEnvelope<TData> | ApiErrorEnvelope;

export interface CreateSessionRequest {
  scenario_id: string;
  symbol: string;
  agent_profile_set: string;
  start_tick_id: string;
  end_tick_id: string;
  tick_interval: string;
}

export interface CreateSessionData {
  session_id: string;
  status: SessionStatus;
  current_tick_id: string;
  websocket_url: string;
}

export interface SessionData {
  session_id: string;
  status: SessionStatus;
  current_tick_id: string;
  tick_state?: TickState;
  agent_count: number;
  active_agent_count: number;
  created_at: string;
}

export interface StartSessionRequest {
  mode: "continuous";
}

export interface StartSessionData {
  session_id: string;
  status: SessionStatus;
  accepted: boolean;
}

export interface PauseSessionRequest {
  reason: string;
}

export interface PauseSessionData {
  session_id: string;
  status: SessionStatus;
  pause_after_state?: TickState;
  accepted?: boolean;
}

export interface StepSessionRequest {
  ticks: 1;
}

export interface StepSessionData {
  session_id: string;
  status: SessionStatus;
  scheduled_ticks: 1;
}

export interface StopSessionRequest {
  reason: string;
}

export interface StopSessionData {
  session_id: string;
  status: "completed" | "failed";
  completion_reason: "operator_stop" | "natural_end" | "failed_after_stop" | string;
}

export interface EventsPage {
  events: ServerEventEnvelope[];
  next_from_seq: number;
  has_more: boolean;
}

export interface SnapshotData {
  session_id: string;
  last_seq: number;
  current_tick_id: string;
  tick_state: TickState;
  market: MarketSnapshot | null;
  agents: AgentSummary[];
  audit_graph: AuditGraphPayload;
  causal_chains: CausalChainSummary[];
}

export type WebApiVisibility =
  | "public"
  | "frontend_only"
  | "agent_private_snapshot"
  | "control_only_view";

export type EventType =
  | "runtime.tick_state"
  | "runtime.agent_lifecycle"
  | "market.price"
  | "market.tape_alert"
  | "market.end_of_day"
  | "forum.post"
  | "agent.account_snapshot"
  | "audit.graph"
  | "audit.causal_chain"
  | "system.error";

export interface ServerEventEnvelope<TPayload = EventPayload> {
  schema_version: SchemaVersion;
  seq: number;
  type: EventType;
  session_id: string;
  tick_id: string;
  trace_id: string;
  server_time: string;
  visibility: WebApiVisibility;
  payload: TPayload;
}

export type EventPayload =
  | RuntimeTickStatePayload
  | RuntimeAgentLifecyclePayload
  | MarketPricePayload
  | MarketTapeAlertPayload
  | MarketEndOfDayPayload
  | ForumPostPayload
  | AgentAccountSnapshotPayload
  | AuditGraphPayload
  | AuditCausalChainPayload
  | SystemErrorPayload;

export interface RuntimeTickStatePayload {
  state: TickState;
  previous_state?: TickState;
  active_agent_count: number;
  completed_agent_count: number;
  timeout_agent_count: number;
  can_advance: boolean;
}

export type AgentType =
  | "retail"
  | "hot_money"
  | "mutual_fund"
  | "institution"
  | "national_team"
  | string;

export type LifecycleState =
  | "active"
  | "suspended"
  | "margin_call"
  | "liquidating"
  | "terminated";

export type RiskState =
  | "normal"
  | "warning"
  | "margin_call"
  | "liquidating"
  | "terminated";

export interface RuntimeAgentLifecyclePayload {
  agent_id: string;
  agent_type: AgentType;
  lifecycle_state: LifecycleState;
  reason_code?: string;
  public_label: string;
}

export type LimitState = "normal" | "limit_up" | "limit_down" | "halted";

export interface Level2Snapshot {
  bids: Array<[price: string, quantity: number]>;
  asks: Array<[price: string, quantity: number]>;
}

export interface MarketSnapshot {
  symbol: string;
  last_price: number;
  volume: number;
  limit_state: LimitState;
  level2: Level2Snapshot;
  turnover?: number;
  limit_up?: number;
  limit_down?: number;
}

export interface MarketPricePayload extends MarketSnapshot {
  turnover: number;
  limit_up: number;
  limit_down: number;
}

export interface MarketTapeAlertPayload {
  symbol: string;
  alert_type: string;
  severity: "low" | "medium" | "high";
  public_text: string;
  metrics: Record<string, number>;
}

export interface DragonTigerSeat {
  seat_name: string;
  seat_type: string;
  buy_amount: number;
  sell_amount: number;
  net_amount: number;
}

export interface MarketEndOfDayPayload {
  symbol: string;
  close_price: number;
  volume: number;
  turnover: number;
  dragon_tiger: {
    buy_rank: DragonTigerSeat[];
    sell_rank: DragonTigerSeat[];
  };
}

export interface ForumPostPayload {
  post_id: string;
  author_agent_id: string;
  author_type: AgentType;
  text: string;
  stance: "bullish" | "bearish" | "neutral";
  created_tick_id: string;
}

export interface AgentAccountSnapshotPayload {
  agent_id: string;
  agent_type: AgentType;
  cash: number;
  available_cash: number;
  positions: Record<string, number>;
  available_shares: Record<string, number>;
  frozen_shares: Record<string, number>;
  market_value: number;
  equity: number;
  risk_state: RiskState;
}

export interface AgentSummary {
  agent_id: string;
  agent_type: AgentType;
  lifecycle_state: LifecycleState;
  risk_state: RiskState;
  equity: number;
  position_value: number;
}

export interface AuditGraphNode {
  agent_id: string;
  agent_type: AgentType;
  belief_score: number;
  position_value: number;
  risk_state: RiskState;
}

export interface AuditGraphEdge {
  source: string;
  target: string;
  weight: number;
  reason_ref: string;
  public_reason: string;
}

export interface AuditGraphPayload {
  nodes: AuditGraphNode[];
  edges: AuditGraphEdge[];
}

export type CausalStepType =
  | "official_news"
  | "public_message"
  | "tape_alert"
  | "belief_shift"
  | "order_flow"
  | "price_move"
  | "risk_event"
  | "end_of_day_disclosure";

export interface CausalChainStep {
  step_id: string;
  step_type: CausalStepType;
  tick_id: string;
  actor_id: string;
  event_ref: string;
  label: string;
  public_text: string;
}

export interface CausalChainSummary {
  chain_id: string;
  title: string;
  summary: string;
  last_event_ref: string;
}

export interface AuditCausalChainPayload extends CausalChainSummary {
  steps: CausalChainStep[];
  metrics: {
    price_change_pct: number;
    affected_agent_count: number;
    confidence: number;
  };
}

export interface SystemErrorPayload extends ApiErrorBody {
  details?: Record<string, unknown>;
}
