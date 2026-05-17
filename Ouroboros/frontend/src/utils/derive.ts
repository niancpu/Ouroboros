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
  const byTick = new Map<string, { price: number; volume: number | null; seq: number }>();
  for (const evt of events) {
    if (evt.type !== "market.price") continue;
    const p = evt.payload as { last_price?: unknown; volume?: unknown };
    if (typeof p.last_price !== "number") continue;
    const existing = byTick.get(evt.tick_id);
    if (existing && existing.seq > evt.seq) continue;
    byTick.set(evt.tick_id, {
      price: p.last_price,
      volume: typeof p.volume === "number" ? p.volume : null,
      seq: evt.seq,
    });
  }
  const snapshots = Array.from(byTick, ([tick_id, value]) => ({ tick_id, ...value })).sort((a, b) =>
    a.seq === b.seq ? a.tick_id.localeCompare(b.tick_id) : a.seq - b.seq,
  );

  const bars = snapshots.map((snapshot, index) => {
    const previous = snapshots[index - 1];
    const open = previous?.price ?? snapshot.price;
    const close = snapshot.price;
    const high = Math.max(open, close);
    const low = Math.min(open, close);
    const volume =
      snapshot.volume === null
        ? 0
        : previous?.volume === null || previous?.volume === undefined
          ? snapshot.volume
          : Math.max(snapshot.volume - previous.volume, 0);

    return { tick_id: snapshot.tick_id, open, high, low, close, volume, is_up: close >= open };
  });

  return bars.slice(-24);
}
