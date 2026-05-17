import type {
  AgentAccountSnapshotPayload,
  AuditCausalChainPayload,
  AuditGraphPayload,
  EventsPage,
  ForumPostPayload,
  MarketEndOfDayPayload,
  MarketPricePayload,
  MarketTapeAlertPayload,
  RuntimeAgentLifecyclePayload,
  RuntimeTickStatePayload,
  ServerEventEnvelope,
  SessionData,
  SnapshotData,
} from "./api";

export interface DemoSeed {
  session: SessionData;
  snapshot: SnapshotData;
  eventsPage: EventsPage;
  feedEvents: ServerEventEnvelope[];
  market: {
    price: MarketPricePayload;
    tapeAlerts: MarketTapeAlertPayload[];
    endOfDay: MarketEndOfDayPayload;
  };
  agents: {
    roster: SnapshotData["agents"];
    accountSnapshots: AgentAccountSnapshotPayload[];
    lifecycle: RuntimeAgentLifecyclePayload[];
  };
  audit: {
    graph: AuditGraphPayload;
    causalChains: AuditCausalChainPayload[];
  };
  chronos: {
    tracks: ChronosTrack[];
  };
  dossier: DossierSummary;
}

export interface ChronosTrack {
  track_id: string;
  label: string;
  events: ChronosTrackEvent[];
}

export interface ChronosTrackEvent {
  tick_id: string;
  event_type: "official_news" | "public_forum" | "market_alert";
  visibility: "public";
  source: string;
  public_text: string;
  event_ref: string;
}

export interface DossierSummary {
  session_id: string;
  symbol: string;
  generated_at: string;
  collapse_probability: number;
  headline: string;
  summary: string;
  key_event_refs: string[];
  risk_rank: Array<{
    agent_id: string;
    risk_state: string;
    equity: number;
    public_reason: string;
  }>;
  forumPosts: ForumPostPayload[];
  endOfDay: MarketEndOfDayPayload;
}

export type {
  AgentAccountSnapshotPayload,
  AuditCausalChainPayload,
  AuditGraphPayload,
  EventsPage,
  MarketEndOfDayPayload,
  MarketPricePayload,
  ServerEventEnvelope,
  SnapshotData,
  RuntimeTickStatePayload,
};
