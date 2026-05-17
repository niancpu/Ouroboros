import { useCallback, useEffect, useMemo, useState } from "react";
import {
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
  deriveTickList,
  pickEventsByType,
  pickLatestMarketPrice,
} from "../utils/derive";
import { eventText } from "../utils/eventReader";
import { displaySession, formatTick } from "../utils/format";
import { agentSummaryToGraphNode, type EdgeFilterMode } from "../utils/graph";
import {
  useControlCommand,
  useDerivedVisualState,
  useEvents,
  useRealtime,
  useSession,
  useSnapshot,
  useUI,
} from "../state";
import type {
  AgentSummary,
  MarketSnapshot,
  RuntimeTickStatePayload,
  SnapshotData,
  TickState,
} from "../types/api";
import type { ApiError } from "../api/errors";
import type { ControlAction } from "../state/types";

const EMPTY_MARKET: MarketSnapshot = {
  symbol: "demo_stock",
  last_price: 0,
  volume: 0,
  limit_state: "normal",
  level2: { bids: [], asks: [] },
};

const EMPTY_SNAPSHOT_AGENTS: AgentSummary[] = [];

interface RecommendationProgress {
  state: TickState | "";
  active: number;
  completed: number;
  timeout: number;
  failed: number;
  total: number;
  canAdvance: boolean;
}

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

function controlErrorMessage(action: ControlAction, error: ApiError, sessionStatus: string): string {
  if (error.code === "SESSION_STATE_CONFLICT") {
    if (sessionStatus === "completed") {
      return "本次推演已经结束，不能继续启动或推进。需要继续观察请新建一场推演。";
    }
    if (action === "start" && sessionStatus === "running") {
      return "推演已经在运行中，不需要重复启动。";
    }
    if (action === "step" && sessionStatus === "running") {
      return "推演正在连续运行，不能同时单步推进。请先暂停后再单步。";
    }
    if (action === "pause") {
      return "当前推演不在运行中，不能暂停。";
    }
    return "当前会话状态不允许执行这个操作，请先确认顶部的推演状态。";
  }

  if (error.code === "SESSION_NOT_FOUND") {
    return "当前会话不存在或后端已重启，请回到初始化页重新创建会话。";
  }

  if (error.code === "INTERNAL_ERROR") {
    return "后端处理失败，请稍后重试；如果连续出现，请检查后端服务日志。";
  }

  return error.message || "操作失败，请稍后重试。";
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

  const sessionData =
    session.phase.kind === "active" || session.phase.kind === "terminal"
      ? session.phase.session
      : null;
  const sessionId = sessionData?.session_id ?? null;
  const sessionStatus = sessionData?.status ?? "";
  const currentTickId = sessionData?.current_tick_id ?? "";
  const canStart = sessionStatus === "created" || sessionStatus === "paused";
  const canPause = sessionStatus === "running";
  const canStep = sessionStatus === "created" || sessionStatus === "paused";
  const canStop =
    sessionStatus === "created" || sessionStatus === "running" || sessionStatus === "paused";
  const controlInFlight =
    startCmd.inFlight || pauseCmd.inFlight || stepCmd.inFlight || stopCmd.inFlight;

  const snapshotData: SnapshotData | null =
    snapshot.phase.kind === "ready" ? snapshot.phase.snapshot : null;

  const agentRoster = snapshotData?.agents ?? EMPTY_SNAPSHOT_AGENTS;
  const lifecycleEvents = useMemo(
    () => events.events.filter((e) => e.type === "runtime.agent_lifecycle"),
    [events.events],
  );
  const lifecycleMap = useMemo(
    () => deriveAgentLifecycleMap(snapshotData, lifecycleEvents),
    [snapshotData, lifecycleEvents],
  );
  const auditEvents = useMemo(
    () => events.events.filter((e) => e.type === "audit.graph"),
    [events.events],
  );
  const auditGraph = useMemo(
    () => deriveAuditGraph(snapshotData, auditEvents),
    [snapshotData, auditEvents],
  );
  const tickEvents = useMemo(
    () => events.events.filter((e) => e.type === "runtime.tick_state"),
    [events.events],
  );
  const tickList = useMemo(
    () => deriveTickList(snapshotData, tickEvents, LIVE_FALLBACK_TICKS),
    [snapshotData, tickEvents],
  );
  const marketEvents = useMemo(
    () => events.events.filter((e) => e.type === "market.price"),
    [events.events],
  );
  const latestMarket = useMemo(() => {
    const event = pickLatestMarketPrice(marketEvents);
    if (event) return event.payload as MarketSnapshot;
    if (snapshotData?.market) return snapshotData.market;
    return EMPTY_MARKET;
  }, [marketEvents, snapshotData]);

  const feedEvents = useMemo(
    () => pickEventsByType(events.events, [...FEED_EVENT_TYPES]),
    [events.events],
  );

  const [scrubIndex, setScrubIndex] = useState<number>(-1);
  const [hoveredAgentId, setHoveredAgentId] = useState<string | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
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
  const recommendationProgress = useMemo(
    () => deriveRecommendationProgress({
      tickEvents,
      displayTick,
      snapshotData,
      sessionAgentCount: sessionData?.agent_count ?? agentRoster.length,
      sessionActiveAgentCount: sessionData?.active_agent_count ?? agentRoster.length,
      isStarting: startCmd.inFlight || sessionStatus === "running",
    }),
    [agentRoster.length, displayTick, sessionData, snapshotData, startCmd.inFlight, sessionStatus, tickEvents],
  );

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

  useEffect(() => {
    setSelectedAgentId(null);
    setSelectedReasonRef(null);
  }, [sessionId]);

  const selectedAgentAccount = selectedAgentId ? agentRoster.find((a) => a.agent_id === selectedAgentId) ?? null : null;
  const selectedNode = selectedAgentId
    ? auditGraph.nodes.find((n) => n.agent_id === selectedAgentId)
      ?? (selectedAgentAccount ? agentSummaryToGraphNode(selectedAgentAccount, 0) : null)
    : null;
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
          <EmptyState label="请在初始化页创建会话" />
        </div>
      </section>
    );
  }

  const visualClass = isReplay ? "state-replay" : `state-${visual}`;

  return (
    <section className={`live-page ${visualClass}`}>
      <header className="terminal-header live-terminal-header">
        <span>会话 {sessionId ? displaySession(sessionId) : "—"}</span>
        <span>节拍 {formatTick(displayTick) || "—"}</span>
        <span>状态 {isReplay ? "REPLAY TICK" : visual === "recovering" ? "RECOVERING SNAPSHOT" : labelFrom(sessionStatusLabels, sessionStatus)}</span>
        <span>连接 {labelFrom(connectionLabels, connectionLabelFromPhase(realtime.phase))}</span>
        <div className="control-buttons">
          <IconButton label="开始" onClick={() => { void startCmd.run(); }} disabled={!canStart || controlInFlight}>
            <Play size={14} />
          </IconButton>
          <IconButton label="暂停" onClick={() => { void pauseCmd.run(); }} disabled={!canPause || controlInFlight}>
            <Pause size={14} />
          </IconButton>
          <IconButton label="单步推进" onClick={() => { void stepCmd.run(); }} disabled={!canStep || controlInFlight}>
            <StepForward size={14} />
          </IconButton>
          <IconButton label="停止" onClick={() => { void stopCmd.run(); }} disabled={!canStop || stopCmd.inFlight}>
            <Square size={14} />
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
            <RotateCcw size={14} />
          </IconButton>
        </div>
      </header>

      {(startCmd.error || pauseCmd.error || stepCmd.error || stopCmd.error) && (
        <div className="control-error-stack">
          {startCmd.error && <ErrorBar code={startCmd.error.code} message={controlErrorMessage("start", startCmd.error, sessionStatus)} onDismiss={startCmd.clearError} />}
          {pauseCmd.error && <ErrorBar code={pauseCmd.error.code} message={controlErrorMessage("pause", pauseCmd.error, sessionStatus)} onDismiss={pauseCmd.clearError} />}
          {stepCmd.error && <ErrorBar code={stepCmd.error.code} message={controlErrorMessage("step", stepCmd.error, sessionStatus)} onDismiss={stepCmd.clearError} />}
          {stopCmd.error && <ErrorBar code={stopCmd.error.code} message={controlErrorMessage("stop", stopCmd.error, sessionStatus)} onDismiss={stopCmd.clearError} />}
        </div>
      )}

      {snapshot.phase.kind === "error" && (
        <div className="live-empty">
          <ErrorBar code={snapshot.phase.error.code} message={`[snapshot] ${snapshot.phase.error.message}`} />
          <EmptyState label="快照不可用，请稍后重试" />
        </div>
      )}

      {snapshot.phase.kind === "loading" && (
        <div className="live-empty">
          <LoadingSkeleton label="LOADING SNAPSHOT" />
        </div>
      )}

      {(snapshot.phase.kind === "ready" || snapshot.phase.kind === "idle") && (
        <div className="live-columns">
          <aside className="left-sidebar">
            <AgentInspectorPanel
              selectedAgent={selectedAgentAccount}
              selectedNode={selectedNode}
              selectedEdges={selectedEdges}
              allNodes={auditGraph.nodes}
              onSelectReason={setSelectedReasonRef}
            />
            <section className="chronos-feed">
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
            </section>
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
              onSelectAgent={setSelectedAgentId}
              onSelectReason={setSelectedReasonRef}
              onEdgeModeChange={setEdgeMode}
            />
            <TickScrubber
              currentIndex={effectiveScrubIndex}
              ticks={tickList}
              onChange={(index) => setScrubIndex(index)}
            />
          </section>

          <aside className="order-book">
            <RecommendationStatusPanel progress={recommendationProgress} />
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

    </section>
  );
}

function RecommendationStatusPanel({ progress }: { progress: RecommendationProgress }) {
  const percent = progress.total > 0 ? Math.round((progress.completed / progress.total) * 100) : 0;
  const pending = Math.max(progress.total - progress.completed - progress.timeout - progress.failed, 0);
  return (
    <aside className="recommendation-status" aria-label="当前推荐进度">
      <h2>推荐进度</h2>
      <div className="recommendation-meter">
        <span style={{ width: `${percent}%` }} />
      </div>
      <strong>{percent}%</strong>
      <div className="recommendation-grid">
        <span>阶段</span>
        <b>{tickStateLabel(progress.state)}</b>
        <span>完成</span>
        <b>{progress.completed}/{progress.total}</b>
        <span>等待</span>
        <b>{pending}</b>
        <span>超时</span>
        <b>{progress.timeout}</b>
        <span>失败</span>
        <b>{progress.failed}</b>
        <span>活跃</span>
        <b>{progress.active}</b>
        <span>可推进</span>
        <b>{progress.canAdvance ? "是" : "否"}</b>
      </div>
    </aside>
  );
}

function deriveRecommendationProgress({
  tickEvents,
  displayTick,
  snapshotData,
  sessionAgentCount,
  sessionActiveAgentCount,
  isStarting,
}: {
  tickEvents: ReadonlyArray<{ tick_id: string; payload: unknown }>;
  displayTick: string;
  snapshotData: SnapshotData | null;
  sessionAgentCount: number;
  sessionActiveAgentCount: number;
  isStarting: boolean;
}): RecommendationProgress {
  const event = pickTickStateEvent(tickEvents, displayTick);
  if (event) {
    const payload = event.payload as RuntimeTickStatePayload;
    const active = normalizeCount(payload.active_agent_count);
    const completed = normalizeCount(payload.completed_agent_count);
    const timeout = normalizeCount(payload.timeout_agent_count);
    const failed = normalizeCount(payload.failed_agent_count);
    return {
      state: payload.state,
      active,
      completed,
      timeout,
      failed,
      total: Math.max(active, completed + timeout + failed, sessionAgentCount, 0),
      canAdvance: Boolean(payload.can_advance),
    };
  }

  const total = Math.max(sessionAgentCount, snapshotData?.agents.length ?? 0);
  if (isStarting && total > 0) {
    return {
      state: snapshotData?.tick_state ?? "INIT_TICK",
      active: Math.max(sessionActiveAgentCount, total),
      completed: 0,
      timeout: 0,
      failed: 0,
      total,
      canAdvance: false,
    };
  }

  return {
    state: snapshotData?.tick_state ?? "",
    active: Math.max(sessionActiveAgentCount, total),
    completed: snapshotData?.tick_state === "COMMIT_TICK" ? total : 0,
    timeout: 0,
    failed: 0,
    total,
    canAdvance: snapshotData?.tick_state === "COMMIT_TICK",
  };
}

function pickTickStateEvent(
  tickEvents: ReadonlyArray<{ tick_id: string; payload: unknown; seq?: number }>,
  displayTick: string,
) {
  const matching = displayTick ? tickEvents.filter((event) => event.tick_id === displayTick) : tickEvents;
  return matching[matching.length - 1] ?? tickEvents[tickEvents.length - 1] ?? null;
}

function normalizeCount(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? Math.max(0, value) : 0;
}

function tickStateLabel(state: TickState | ""): string {
  switch (state) {
    case "CHRONOS_SEED":
      return "生成公开输入";
    case "INIT_TICK":
      return "初始化节拍";
    case "RELEASE_FACTS":
      return "释放公开输入";
    case "PUBLISH_MARKET_VIEW":
      return "发布行情视图";
    case "PAYLOAD_SPLIT":
      return "分发输入";
    case "AGENT_STEP":
      return "智能体推荐";
    case "BARRIER_WAIT":
      return "等待智能体屏障";
    case "MATCH_AND_CLEAR":
      return "撮合清算";
    case "RISK_AND_LIFECYCLE":
      return "风险与生命周期";
    case "REFEREE_PUBLICATION":
      return "发布审计结果";
    case "COMMIT_TICK":
      return "提交节拍";
    case "FAILED":
      return "失败";
    default:
      return "等待数据";
  }
}
