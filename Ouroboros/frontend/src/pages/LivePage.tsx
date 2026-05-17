import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Network,
  Pause,
  Play,
  RotateCcw,
  Square,
  StepForward,
} from "lucide-react";
import { ErrorBar } from "../components/shell/ErrorBar";
import { IconButton } from "../components/common/IconButton";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingSkeleton } from "../components/common/LoadingSkeleton";
import { AgentInspectorPanel } from "../components/live/AgentInspectorPanel";
import { BookSide } from "../components/live/BookSide";
import { MarketCurves } from "../components/live/MarketCurves";
import { TickScrubber } from "../components/live/TickScrubber";
import { Topology } from "../components/live/Topology";
import { FEED_EVENT_TYPES, LIVE_FALLBACK_TICKS } from "../config/constants";
import {
  connectionLabels,
  eventTypeLabels,
  labelFrom,
  sessionStatusLabels,
} from "../i18n/labels";
import {
  deriveAgentLifecycleMap,
  deriveAuditGraph,
  derivePriceHistory,
  deriveTickList,
  pickEventsByType,
  pickLatestMarketPrice,
} from "../utils/derive";
import { eventText } from "../utils/eventReader";
import { displaySession, formatTick } from "../utils/format";
import type { EdgeFilterMode } from "../utils/graph";
import {
  useControlCommand,
  useDerivedVisualState,
  useEvents,
  useRealtime,
  useSession,
  useSnapshot,
  useUI,
} from "../state";
import type { AgentSummary, MarketSnapshot, SnapshotData } from "../types/api";

const EMPTY_MARKET: MarketSnapshot = {
  symbol: "demo_stock",
  last_price: 0,
  volume: 0,
  limit_state: "normal",
  level2: { bids: [], asks: [] },
};

const EMPTY_SNAPSHOT_AGENTS: AgentSummary[] = [];

function connectionLabelFromPhase(phase: ReturnType<typeof useRealtime>["phase"]): string {
  switch (phase.kind) {
    case "idle":
      return "IDLE";
    case "connecting":
      return "CONNECTING";
    case "open":
      return "OPEN";
    case "recovering":
      return "RECOVERING";
    case "closed":
      return "CLOSED";
    case "error":
      return phase.error.code === "INTERNAL_ERROR" ? "BACKEND_UNREACHABLE" : "ERROR";
  }
}

export function LivePage() {
  const session = useSession();
  const snapshot = useSnapshot();
  const events = useEvents();
  const realtime = useRealtime();
  const ui = useUI();
  const visual = useDerivedVisualState();

  const startCmd = useControlCommand("start");
  const pauseCmd = useControlCommand("pause");
  const stepCmd = useControlCommand("step");
  const stopCmd = useControlCommand("stop");

  const sessionId = session.phase.kind === "active" ? session.phase.session.session_id : null;
  const sessionStatus = session.phase.kind === "active" ? session.phase.session.status : "";
  const currentTickId = session.phase.kind === "active" ? session.phase.session.current_tick_id : "";

  const snapshotData: SnapshotData | null =
    snapshot.phase.kind === "ready" ? snapshot.phase.snapshot : null;

  const agentRoster = snapshotData?.agents ?? EMPTY_SNAPSHOT_AGENTS;
  const lifecycleMap = useMemo(
    () => deriveAgentLifecycleMap(snapshotData, events.events),
    [snapshotData, events.events],
  );
  const auditGraph = useMemo(
    () => deriveAuditGraph(snapshotData, events.events),
    [snapshotData, events.events],
  );
  const tickList = useMemo(
    () => deriveTickList(snapshotData, events.events, LIVE_FALLBACK_TICKS),
    [snapshotData, events.events],
  );
  const priceHistory = useMemo(() => derivePriceHistory(events.events), [events.events]);
  const latestMarket = useMemo(() => {
    const event = pickLatestMarketPrice(events.events);
    if (event) return event.payload as MarketSnapshot;
    if (snapshotData) return snapshotData.market;
    return EMPTY_MARKET;
  }, [events.events, snapshotData]);

  const feedEvents = useMemo(
    () => pickEventsByType(events.events, [...FEED_EVENT_TYPES]),
    [events.events],
  );

  const [scrubIndex, setScrubIndex] = useState<number>(-1);
  const [hoveredAgentId, setHoveredAgentId] = useState<string | null>(null);
  const [selectedReasonRef, setSelectedReasonRef] = useState<string | null>(null);
  const [edgeMode, setEdgeMode] = useState<EdgeFilterMode>("current");

  const liveTickIndex = useMemo(() => {
    const idx = tickList.indexOf(currentTickId);
    if (idx >= 0) return idx;
    return Math.max(tickList.length - 1, 0);
  }, [tickList, currentTickId]);

  const effectiveScrubIndex = scrubIndex < 0 ? liveTickIndex : scrubIndex;
  const displayTick = tickList[effectiveScrubIndex] ?? currentTickId ?? "";

  const isReplay = scrubIndex >= 0 && scrubIndex !== liveTickIndex;

  const startRealtime = useCallback(() => {
    if (session.phase.kind !== "active") return;
    if (snapshot.phase.kind !== "ready") return;
    realtime.start(session.phase.session.session_id, snapshot.phase.snapshot.last_seq, {
      onEvent: (event) => events.append(event),
      onSnapshotRequired: () => {
        events.reset();
        if (session.phase.kind === "active") {
          void snapshot.load(session.phase.session.session_id);
        }
      },
    });
  }, [session, snapshot, events, realtime]);

  useEffect(() => {
    if (session.phase.kind !== "active") return;
    if (snapshot.phase.kind === "idle") {
      void snapshot.load(session.phase.session.session_id);
    }
  }, [session, snapshot]);

  useEffect(() => {
    if (snapshot.phase.kind !== "ready") return;
    if (realtime.phase.kind !== "idle" && realtime.phase.kind !== "closed") return;
    startRealtime();
  }, [snapshot.phase, realtime.phase, startRealtime]);

  useEffect(() => {
    return () => {
      realtime.stop("unmount");
    };
    // realtime intentionally captured at mount; stop is stable via useCallback
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedAgentId = ui.selectedAgentId;
  const selectedAgentAccount = selectedAgentId ? agentRoster.find((a) => a.agent_id === selectedAgentId) ?? null : null;
  const selectedNode = selectedAgentId ? auditGraph.nodes.find((n) => n.agent_id === selectedAgentId) ?? null : null;
  const selectedEdges = selectedAgentId
    ? auditGraph.edges.filter((e) => e.source === selectedAgentId || e.target === selectedAgentId)
    : [];

  if (session.phase.kind === "none") {
    return (
      <section className="live-page state-empty">
        <header className="terminal-header live-terminal-header">
          <span>Ouroboros 实时推演</span>
          <span>NO SESSION</span>
        </header>
        <div className="live-empty">
          <EmptyState label="NO SESSION // 请在初始化页创建会话" />
        </div>
      </section>
    );
  }

  const visualClass = isReplay ? "state-replay" : `state-${visual}`;

  return (
    <section className={`live-page ${visualClass}`}>
      <header className="terminal-header live-terminal-header">
        <span>Ouroboros 实时推演</span>
        <span>会话 {sessionId ? displaySession(sessionId) : "—"}</span>
        <span>节拍 {formatTick(displayTick) || "—"}</span>
        <span>{isReplay ? "REPLAY TICK" : visual === "recovering" ? "RECOVERING SNAPSHOT" : labelFrom(sessionStatusLabels, sessionStatus)}</span>
        <span>{labelFrom(connectionLabels, connectionLabelFromPhase(realtime.phase))}</span>
        <div className="control-buttons">
          <IconButton label="开始" onClick={() => { void startCmd.run(); }} disabled={startCmd.inFlight}>
            <Play size={16} />
          </IconButton>
          <IconButton label="暂停" onClick={() => { void pauseCmd.run(); }} disabled={pauseCmd.inFlight}>
            <Pause size={16} />
          </IconButton>
          <IconButton label="单步推进" onClick={() => { void stepCmd.run(); }} disabled={stepCmd.inFlight}>
            <StepForward size={16} />
          </IconButton>
          <IconButton label="停止" onClick={() => { void stopCmd.run(); }} disabled={stopCmd.inFlight}>
            <Square size={16} />
          </IconButton>
          <IconButton
            label="恢复快照"
            onClick={() => {
              if (session.phase.kind === "active") {
                events.reset();
                void snapshot.load(session.phase.session.session_id);
              }
            }}
          >
            <RotateCcw size={16} />
          </IconButton>
        </div>
      </header>

      {(startCmd.error || pauseCmd.error || stepCmd.error || stopCmd.error) && (
        <div className="control-error-stack">
          {startCmd.error && <ErrorBar code={startCmd.error.code} message={`[start] ${startCmd.error.message}`} onDismiss={startCmd.clearError} />}
          {pauseCmd.error && <ErrorBar code={pauseCmd.error.code} message={`[pause] ${pauseCmd.error.message}`} onDismiss={pauseCmd.clearError} />}
          {stepCmd.error && <ErrorBar code={stepCmd.error.code} message={`[step] ${stepCmd.error.message}`} onDismiss={stepCmd.clearError} />}
          {stopCmd.error && <ErrorBar code={stopCmd.error.code} message={`[stop] ${stopCmd.error.message}`} onDismiss={stopCmd.clearError} />}
        </div>
      )}

      {snapshot.phase.kind === "error" && (
        <div className="live-empty">
          <ErrorBar code={snapshot.phase.error.code} message={`[snapshot] ${snapshot.phase.error.message}`} />
          <EmptyState label="SNAPSHOT UNAVAILABLE // 请稍后重试或检查后端" />
        </div>
      )}

      {snapshot.phase.kind === "loading" && (
        <div className="live-empty">
          <LoadingSkeleton label="LOADING SNAPSHOT" />
        </div>
      )}

      {(snapshot.phase.kind === "ready" || snapshot.phase.kind === "idle") && (
        <div className="live-columns">
          <aside className="chronos-feed">
            <h2>时间轴事件流</h2>
            {feedEvents.length === 0 ? (
              <EmptyState label="NO EVENTS YET" />
            ) : (
              feedEvents.map((event) => {
                const reasonRef = typeof event.payload === "object" && event.payload !== null
                  ? (event.payload as { post_id?: string; reason_ref?: string }).post_id ??
                    (event.payload as { reason_ref?: string }).reason_ref
                  : undefined;
                return (
                  <article
                    className={reasonRef && reasonRef === selectedReasonRef ? "sync-highlight" : ""}
                    key={`${event.seq}-${event.type}`}
                  >
                    <time>{formatTick(event.tick_id)}</time>
                    <strong>{labelFrom(eventTypeLabels, event.type)}</strong>
                    <p>{eventText(event)}</p>
                  </article>
                );
              })
            )}
          </aside>

          <section className="canvas-stack">
            <Topology
              agents={agentRoster}
              graph={auditGraph}
              agentLifecycleMap={lifecycleMap}
              edgeMode={edgeMode}
              hoveredAgentId={hoveredAgentId}
              selectedAgentId={selectedAgentId}
              selectedReasonRef={selectedReasonRef}
              tickId={displayTick}
              onHoverAgent={setHoveredAgentId}
              onSelectAgent={ui.setSelectedAgentId}
              onSelectReason={setSelectedReasonRef}
              onEdgeModeChange={setEdgeMode}
            />
            <TickScrubber
              currentIndex={effectiveScrubIndex}
              ticks={tickList}
              onChange={(index) => setScrubIndex(index)}
            />
            <MarketCurves market={latestMarket} priceHistory={priceHistory} />
          </section>

          <aside className="order-book inspector-book">
            <AgentInspectorPanel
              selectedAgent={selectedAgentAccount}
              selectedNode={selectedNode}
              selectedEdges={selectedEdges}
              allNodes={auditGraph.nodes}
              onSelectReason={setSelectedReasonRef}
            />
            <h2>盘口</h2>
            {latestMarket.level2.asks.length || latestMarket.level2.bids.length ? (
              <>
                <BookSide title="卖盘" rows={latestMarket.level2.asks} side="sell" />
                <BookSide title="买盘" rows={latestMarket.level2.bids} side="buy" />
              </>
            ) : (
              <EmptyState label="NO LEVEL2 DATA" />
            )}
          </aside>
        </div>
      )}

      <header className="live-footer">
        <span>显示节拍：<Network size={12} /> {formatTick(displayTick) || "—"}</span>
        {isReplay && <span className="replay-badge">REPLAY</span>}
      </header>
    </section>
  );
}
