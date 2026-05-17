import { useEffect, useMemo, useState } from "react";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingSkeleton } from "../components/common/LoadingSkeleton";
import { LIVE_FALLBACK_TICKS } from "../config/constants";
import { useEvents, useSession, useSnapshot } from "../state";
import { getRestClient } from "../state/restSingleton";
import { deriveTickList, pickEventsByType } from "../utils/derive";
import { displaySession, formatTick } from "../utils/format";
import type {
  ForumPostPayload,
  MarketEndOfDayPayload,
  MarketTapeAlertPayload,
  ServerEventEnvelope,
  SnapshotData,
  WebApiVisibility,
} from "../types/api";

interface OfficialItem {
  id: string;
  tick_id: string;
  title: string;
  public_text: string;
  source: string;
  visibility: WebApiVisibility;
  event_ref: string;
}

interface RumorItem {
  id: string;
  tick_id: string;
  public_text: string;
  source: string;
  visibility: WebApiVisibility;
  event_ref: string;
}

interface DraftItem {
  id: string;
  tick_id: string;
  event_type: string;
  visibility: WebApiVisibility;
  source: string;
  audit_reason: string;
}

type TimelineMarkerKind = "past" | "current" | "future" | "draft";

interface TimelineMarker {
  tick_id: string;
  kind: TimelineMarkerKind;
  label: string;
}

function readForumPost(event: ServerEventEnvelope): RumorItem {
  const payload = event.payload as ForumPostPayload;
  return {
    id: payload.post_id,
    tick_id: event.tick_id,
    public_text: payload.text,
    source: `公开论坛 / ${payload.author_type}`,
    visibility: event.visibility,
    event_ref: payload.post_id,
  };
}

function readTapeAlert(event: ServerEventEnvelope): RumorItem {
  const payload = event.payload as MarketTapeAlertPayload;
  return {
    id: `tape_${event.seq}`,
    tick_id: event.tick_id,
    public_text: payload.public_text,
    source: `盘口异动 / ${payload.severity}`,
    visibility: event.visibility,
    event_ref: `seq_${event.seq}`,
  };
}

function readOfficial(event: ServerEventEnvelope): OfficialItem | null {
  if (event.type !== "market.end_of_day") return null;
  const payload = event.payload as MarketEndOfDayPayload;
  const strongestBuy = payload.dragon_tiger.buy_rank[0];
  const strongestSell = payload.dragon_tiger.sell_rank[0];
  const parts = [
    `收盘价 ${payload.close_price.toFixed(2)}`,
    `成交量 ${payload.volume.toLocaleString("en-US")}`,
    strongestBuy ? `买一席位 ${strongestBuy.seat_name}` : null,
    strongestSell ? `卖一席位 ${strongestSell.seat_name}` : null,
  ].filter((part): part is string => Boolean(part));
  return {
    id: `eod_${event.seq}`,
    tick_id: event.tick_id,
    title: "盘后披露",
    public_text: parts.join("；"),
    source: "交易所公开披露",
    visibility: event.visibility,
    event_ref: `seq_${event.seq}`,
  };
}

function buildTickRange(start: string | undefined, end: string | undefined): string[] {
  if (!start || !end) return [];
  const startMs = Date.parse(start);
  const endMs = Date.parse(end);
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || startMs >= endMs) {
    return [start, end].filter((tick, index, arr) => tick && arr.indexOf(tick) === index);
  }

  const steps = 7;
  const values: string[] = [];
  for (let index = 0; index < steps; index += 1) {
    const ratio = index / (steps - 1);
    const date = new Date(startMs + (endMs - startMs) * ratio);
    values.push(formatTickId(date));
  }
  return Array.from(new Set(values));
}

function formatTickId(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return [
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`,
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}+08:00`,
  ].join("");
}

function sortByTickThenId<T extends { tick_id: string; id: string }>(items: T[]): T[] {
  return [...items].sort((a, b) => {
    const byTick = a.tick_id.localeCompare(b.tick_id);
    return byTick === 0 ? a.id.localeCompare(b.id) : byTick;
  });
}

export function ChronosPage() {
  const session = useSession();
  const snapshot = useSnapshot();
  const events = useEvents();
  const appendBatch = events.appendBatch;
  const [replayStatus, setReplayStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [replayEvents, setReplayEvents] = useState<ServerEventEnvelope[]>([]);

  const snapshotData: SnapshotData | null =
    snapshot.phase.kind === "ready" ? snapshot.phase.snapshot : null;

  const sessionData =
    session.phase.kind === "active" || session.phase.kind === "terminal"
      ? session.phase.session
      : null;

  useEffect(() => {
    if (!sessionData?.session_id) {
      setReplayStatus("idle");
      setReplayEvents([]);
      return;
    }

    let cancelled = false;
    const rest = getRestClient();

    async function loadReplay() {
      setReplayStatus("loading");
      try {
        const collected: ServerEventEnvelope[] = [];
        let fromSeq = 0;
        for (let pageIndex = 0; pageIndex < 10; pageIndex += 1) {
          const page = await rest.getEvents(sessionData!.session_id, { fromSeq, limit: 500 });
          collected.push(...page.events);
          if (!page.has_more || page.next_from_seq === fromSeq) break;
          fromSeq = page.next_from_seq;
        }
        if (!cancelled) {
          setReplayEvents(collected);
          appendBatch(collected);
          setReplayStatus("ready");
        }
      } catch {
        if (!cancelled) {
          setReplayStatus("error");
          setReplayEvents([]);
        }
      }
    }

    void loadReplay();

    return () => {
      cancelled = true;
    };
  }, [appendBatch, sessionData?.session_id]);

  const visibleEvents = useMemo(() => {
    const bySeq = new Map<number, ServerEventEnvelope>();
    for (const event of replayEvents) bySeq.set(event.seq, event);
    for (const event of events.events) bySeq.set(event.seq, event);
    return Array.from(bySeq.values()).sort((a, b) => a.seq - b.seq);
  }, [events.events, replayEvents]);

  const tickList = useMemo(
    () => {
      const range = buildTickRange(sessionData?.start_tick_id, sessionData?.end_tick_id);
      const derived = deriveTickList(snapshotData, visibleEvents, LIVE_FALLBACK_TICKS);
      return Array.from(new Set([...range, ...derived])).sort();
    },
    [sessionData?.end_tick_id, sessionData?.start_tick_id, snapshotData, visibleEvents],
  );

  const currentTickId = sessionData?.current_tick_id ?? null;

  const localDrafts = useMemo<DraftItem[]>(() => {
    const futureTicks = tickList.filter((tick) => currentTickId && tick > currentTickId).slice(0, 3);
    return futureTicks.map((tick, index) => ({
      id: `local_draft_${tick}_${index}`,
      tick_id: tick,
      event_type: index === 0 ? "官方事实释放" : index === 1 ? "公开传闻观察" : "盘口异动预警",
      visibility: "public",
      source: "本地草案预览",
      audit_reason: "只读预览，不写入 REST、WebSocket 或 Chronos SSOT",
    }));
  }, [currentTickId, tickList]);

  const timelineMarkers = useMemo<TimelineMarker[]>(() => {
    const draftTicks = new Set(localDrafts.map((draft) => draft.tick_id));
    return tickList.map((tick) => {
      let kind: TimelineMarkerKind = "past";
      if (tick === currentTickId) kind = "current";
      else if (draftTicks.has(tick)) kind = "draft";
      else if (currentTickId && tick > currentTickId) kind = "future";
      return {
        tick_id: tick,
        kind,
        label: kind === "draft" ? "本地草案占位" : kind === "future" ? "未来占位" : formatTick(tick),
      };
    });
  }, [currentTickId, localDrafts, tickList]);

  const officialItems = useMemo(() => {
    const subset = pickEventsByType(visibleEvents, ["market.end_of_day"]);
    return sortByTickThenId(subset
      .map(readOfficial)
      .filter((item): item is OfficialItem => item !== null));
  }, [visibleEvents]);

  const rumorItems = useMemo(() => {
    const forum = pickEventsByType(visibleEvents, ["forum.post"]).map(readForumPost);
    const tape = pickEventsByType(visibleEvents, ["market.tape_alert"]).map(readTapeAlert);
    return sortByTickThenId([...forum, ...tape]);
  }, [visibleEvents]);

  if (session.phase.kind === "none") {
    return (
      <section className="chronos-page">
        <header className="terminal-header">
          <span>时间轴剧本管理</span>
          <span>READ ONLY TIMELINE</span>
        </header>
        <EmptyState label="NO SESSION" />
      </section>
    );
  }

  if (snapshot.phase.kind === "loading") {
    return (
      <section className="chronos-page">
        <header className="terminal-header">
          <span>时间轴剧本管理</span>
          <span>READ ONLY TIMELINE</span>
        </header>
        <LoadingSkeleton label="LOADING TIMELINE" />
      </section>
    );
  }

  return (
    <section className="chronos-page">
      <header className="terminal-header">
        <span>时间轴剧本管理</span>
        <span>READ ONLY TIMELINE</span>
        {sessionData && <span>{displaySession(sessionData.session_id)}</span>}
        <span>{formatTick(currentTickId ?? "")}</span>
      </header>
      <div className="timeline">
        {timelineMarkers.map((marker) => (
          <span
            className={marker.kind}
            key={marker.tick_id}
            title={`${formatTick(marker.tick_id)} / ${marker.label}`}
          />
        ))}
      </div>
      <div className="chronos-tracks">
        <section className="official-track">
          <header>
            <h2>官方事实轨</h2>
            <span>已公开释放</span>
          </header>
          {officialItems.length === 0 ? (
            <EmptyState label="NO OFFICIAL EVENTS" />
          ) : (
            officialItems.map((item) => (
              <article key={item.id}>
                <time>{formatTick(item.tick_id)}</time>
                <h3>{item.title}</h3>
                <p>{item.public_text}</p>
                <small>{item.source} / {item.visibility} / {item.event_ref}</small>
              </article>
            ))
          )}
        </section>
        <section className="rumor-track">
          <header>
            <h2>公开传闻轨</h2>
            <span>论坛与盘口公开消息</span>
          </header>
          {rumorItems.length === 0 ? (
            <EmptyState label="NO PUBLIC RUMORS" />
          ) : (
            rumorItems.map((item) => (
              <article key={item.id}>
                <time>{formatTick(item.tick_id)}</time>
                <p>{item.public_text}</p>
                <small>{item.source} / {item.visibility} / {item.event_ref}</small>
              </article>
            ))
          )}
        </section>
        <section className="draft-track">
          <header>
            <h2>LOCAL DRAFT</h2>
            <span>{replayStatus === "loading" ? "正在回放事件" : "仅本地预览"}</span>
          </header>
          {localDrafts.length === 0 ? (
            <EmptyState label="NO FUTURE SLOTS" />
          ) : (
            localDrafts.map((item) => (
              <article key={item.id}>
                <time>{formatTick(item.tick_id)}</time>
                <strong>{item.event_type}</strong>
                <p>{item.source} / {item.visibility}</p>
                <small>{item.audit_reason}</small>
              </article>
            ))
          )}
          {replayStatus === "error" && (
            <p className="chronos-warning">事件回放不可用，当前只显示已缓存的实时事件。</p>
          )}
        </section>
      </div>
    </section>
  );
}
