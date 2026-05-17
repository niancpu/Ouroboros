import type {
  AgentAccountSnapshotPayload,
  AuditCausalChainPayload,
  AuditGraphPayload,
  LifecycleState,
  RuntimeAgentLifecyclePayload,
  ServerEventEnvelope,
  SnapshotData,
} from "../types/api";

export function deriveTickList(
  snapshot: SnapshotData | null,
  events: ReadonlyArray<ServerEventEnvelope>,
  fallback: ReadonlyArray<string>,
): string[] {
  const set = new Set<string>();
  if (snapshot?.current_tick_id) set.add(snapshot.current_tick_id);
  for (const evt of events) {
    if (evt.tick_id) set.add(evt.tick_id);
  }
  if (set.size === 0) return [...fallback];
  return Array.from(set).sort();
}

export function derivePriceHistory(events: ReadonlyArray<ServerEventEnvelope>): number[] {
  const prices: number[] = [];
  for (const evt of events) {
    if (evt.type !== "market.price") continue;
    const payload = evt.payload as { last_price?: unknown };
    if (typeof payload.last_price === "number") prices.push(payload.last_price);
  }
  return prices.slice(-24);
}

export function deriveAgentLifecycleMap(
  snapshot: SnapshotData | null,
  events: ReadonlyArray<ServerEventEnvelope>,
): Map<string, LifecycleState> {
  const map = new Map<string, LifecycleState>();
  if (snapshot) {
    for (const agent of snapshot.agents) {
      map.set(agent.agent_id, agent.lifecycle_state);
    }
  }
  for (const evt of events) {
    if (evt.type !== "runtime.agent_lifecycle") continue;
    const payload = evt.payload as RuntimeAgentLifecyclePayload;
    map.set(payload.agent_id, payload.lifecycle_state);
  }
  return map;
}

export function deriveAccountSnapshots(
  events: ReadonlyArray<ServerEventEnvelope>,
): Map<string, AgentAccountSnapshotPayload> {
  const map = new Map<string, AgentAccountSnapshotPayload>();
  for (const evt of events) {
    if (evt.type !== "agent.account_snapshot") continue;
    const payload = evt.payload as AgentAccountSnapshotPayload;
    map.set(payload.agent_id, payload);
  }
  return map;
}

export function deriveCausalChains(
  snapshot: SnapshotData | null,
  events: ReadonlyArray<ServerEventEnvelope>,
): AuditCausalChainPayload[] {
  const map = new Map<string, AuditCausalChainPayload>();
  if (snapshot) {
    for (const summary of snapshot.causal_chains) {
      map.set(summary.chain_id, {
        chain_id: summary.chain_id,
        title: summary.title,
        summary: summary.summary,
        last_event_ref: summary.last_event_ref,
        steps: [],
        metrics: { price_change_pct: 0, affected_agent_count: 0, confidence: 0 },
      });
    }
  }
  for (const evt of events) {
    if (evt.type !== "audit.causal_chain") continue;
    const payload = evt.payload as AuditCausalChainPayload;
    map.set(payload.chain_id, payload);
  }
  return Array.from(map.values());
}

export function deriveAuditGraph(
  snapshot: SnapshotData | null,
  events: ReadonlyArray<ServerEventEnvelope>,
): AuditGraphPayload {
  const base: AuditGraphPayload = snapshot?.audit_graph ?? { nodes: [], edges: [] };
  let latest: AuditGraphPayload | null = null;
  for (const evt of events) {
    if (evt.type === "audit.graph") {
      latest = evt.payload as AuditGraphPayload;
    }
  }
  return latest ?? base;
}

export function pickEventsByType(
  events: ReadonlyArray<ServerEventEnvelope>,
  types: ReadonlyArray<string>,
): ServerEventEnvelope[] {
  return events.filter((evt) => types.includes(evt.type));
}

export function pickLatestMarketPrice(
  events: ReadonlyArray<ServerEventEnvelope>,
): ServerEventEnvelope | null {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    if (events[i].type === "market.price") return events[i];
  }
  return null;
}

export interface OHLCVBar {
  tick_id: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  is_up: boolean; // close >= open
}

export function deriveOHLCV(
  events: ReadonlyArray<ServerEventEnvelope>,
): OHLCVBar[] {
  // Group market.price events by tick_id
  const byTick = new Map<string, { prices: number[]; volumes: number[] }>();
  for (const evt of events) {
    if (evt.type !== "market.price") continue;
    const p = evt.payload as { last_price?: unknown; volume?: unknown };
    if (typeof p.last_price !== "number") continue;
    const bucket = byTick.get(evt.tick_id) ?? { prices: [], volumes: [] };
    bucket.prices.push(p.last_price);
    if (typeof p.volume === "number") bucket.volumes.push(p.volume);
    byTick.set(evt.tick_id, bucket);
  }
  const bars: OHLCVBar[] = [];
  for (const [tick_id, { prices, volumes }] of byTick) {
    if (prices.length === 0) continue;
    const open = prices[0];
    const close = prices[prices.length - 1];
    const high = Math.max(...prices);
    const low = Math.min(...prices);
    const volume = volumes.length > 0 ? volumes[volumes.length - 1] : 0;
    bars.push({ tick_id, open, high, low, close, volume, is_up: close >= open });
  }
  // Sort by tick_id (string sort works for tick IDs like "T001", "T002")
  bars.sort((a, b) => a.tick_id.localeCompare(b.tick_id));
  return bars.slice(-24); // keep last 24 candles max
}
