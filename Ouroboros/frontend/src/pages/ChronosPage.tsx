import { useMemo } from "react";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingSkeleton } from "../components/common/LoadingSkeleton";
import { LIVE_FALLBACK_TICKS } from "../config/constants";
import { useEvents, useSession, useSnapshot } from "../state";
import { deriveTickList, pickEventsByType } from "../utils/derive";
import { displaySession, formatTick } from "../utils/format";
import type { ForumPostPayload, MarketTapeAlertPayload, ServerEventEnvelope, SnapshotData } from "../types/api";

interface OfficialItem {
  id: string;
  tick_id: string;
  title: string;
  public_text: string;
}

interface RumorItem {
  id: string;
  tick_id: string;
  public_text: string;
}

function readForumPost(event: ServerEventEnvelope): RumorItem {
  const payload = event.payload as ForumPostPayload;
  return {
    id: payload.post_id,
    tick_id: event.tick_id,
    public_text: payload.text,
  };
}

function readTapeAlert(event: ServerEventEnvelope): RumorItem {
  const payload = event.payload as MarketTapeAlertPayload;
  return {
    id: `tape_${event.seq}`,
    tick_id: event.tick_id,
    public_text: payload.public_text,
  };
}

function readOfficial(event: ServerEventEnvelope): OfficialItem | null {
  // 第一版："官方事实轨" 数据源由 Web API 限定，目前仅 market.end_of_day 落入此轨。
  if (event.type !== "market.end_of_day") return null;
  return {
    id: `eod_${event.seq}`,
    tick_id: event.tick_id,
    title: "盘后披露",
    public_text: "收盘统计与龙虎榜已发布。",
  };
}

export function ChronosPage() {
  const session = useSession();
  const snapshot = useSnapshot();
  const events = useEvents();

  const snapshotData: SnapshotData | null =
    snapshot.phase.kind === "ready" ? snapshot.phase.snapshot : null;
  const tickList = useMemo(
    () => deriveTickList(snapshotData, events.events, LIVE_FALLBACK_TICKS),
    [snapshotData, events.events],
  );

  const currentTickId =
    session.phase.kind === "active" ? session.phase.session.current_tick_id : null;

  const officialItems = useMemo(() => {
    const subset = pickEventsByType(events.events, ["market.end_of_day"]);
    return subset
      .map(readOfficial)
      .filter((item): item is OfficialItem => item !== null)
      .sort((a, b) => a.tick_id.localeCompare(b.tick_id));
  }, [events.events]);

  const rumorItems = useMemo(() => {
    const forum = pickEventsByType(events.events, ["forum.post"]).map(readForumPost);
    const tape = pickEventsByType(events.events, ["market.tape_alert"]).map(readTapeAlert);
    return [...forum, ...tape].sort((a, b) => a.tick_id.localeCompare(b.tick_id));
  }, [events.events]);

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
        {session.phase.kind === "active" && (
          <span>{displaySession(session.phase.session.session_id)}</span>
        )}
        <span>{formatTick(currentTickId ?? "")}</span>
      </header>
      <div className="timeline">
        {tickList.map((tick) => {
          const cls = tick === currentTickId
            ? "current"
            : currentTickId && tick > currentTickId
              ? "future"
              : "";
          return <span className={cls} key={tick} title={formatTick(tick)} />;
        })}
      </div>
      <div className="chronos-tracks">
        <section className="official-track">
          <h2>官方事实轨</h2>
          {officialItems.length === 0 ? (
            <EmptyState label="NO OFFICIAL EVENTS" />
          ) : (
            officialItems.map((item) => (
              <article key={item.id}>
                <time>{formatTick(item.tick_id)}</time>
                <h3>{item.title}</h3>
                <p>{item.public_text}</p>
              </article>
            ))
          )}
        </section>
        <section className="rumor-track">
          <h2>公开传闻轨</h2>
          {rumorItems.length === 0 ? (
            <EmptyState label="NO PUBLIC RUMORS" />
          ) : (
            rumorItems.map((item) => (
              <article key={item.id}>
                <time>{formatTick(item.tick_id)}</time>
                <p>{item.public_text}</p>
              </article>
            ))
          )}
        </section>
      </div>
    </section>
  );
}
