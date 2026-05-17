import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Activity, Crosshair, Eye, Network, Play, RotateCcw, Square, StepForward } from "lucide-react";
import "./styles/global.css";
import { seedState } from "./data/seed";
import type { AgentSnapshot, CausalChain, MarketSnapshot, SessionStatus, WebEventEnvelope } from "./types/webApi";
import type { AuditGraphEdge, AuditGraphNode } from "./types/api";

type ModuleKey = "CONFIG" | "LIVE" | "ENTITY" | "CHRONOS" | "DOSSIER";

const modules: ModuleKey[] = ["CONFIG", "LIVE", "ENTITY", "CHRONOS", "DOSSIER"];
const moduleLabels: Record<ModuleKey, string> = {
  CONFIG: "初始化",
  LIVE: "实时推演",
  ENTITY: "智能体",
  CHRONOS: "时间轴",
  DOSSIER: "白皮书",
};

const sessionStatusLabels: Record<string, string> = {
  created: "已创建",
  running: "运行中",
  paused: "已暂停",
  stopped: "已停止",
  completed: "已完成",
};

const connectionLabels: Record<string, string> = {
  DEMO_OFFLINE: "演示离线",
  SESSION_CREATED: "会话已创建",
  CONTROL_RUNNING: "控制：运行中",
  CONTROL_PAUSED: "控制：已暂停",
  CONTROL_STOPPED: "控制：已停止",
  CONTROL_CREATED: "控制：已创建",
  CONTROL_COMPLETED: "控制：已完成",
};

const eventTypeLabels: Record<string, string> = {
  "runtime.tick_state": "运行节拍",
  "market.price": "行情价格",
  "market.tape_alert": "盘口异动",
  "market.end_of_day": "盘后披露",
  "forum.post": "公开论坛",
  "agent.account_snapshot": "账户快照",
  "audit.graph": "审计图谱",
  "audit.causal_chain": "因果链",
  "system.error": "系统错误",
};

const agentTypeLabels: Record<string, string> = {
  mutual_fund: "公募机构",
  hot_money: "游资",
  retail: "散户",
  retail_cluster: "散户集群",
  institution: "机构",
  market: "市场",
};

const riskStateLabels: Record<string, string> = {
  normal: "正常",
  warning: "预警",
  margin_call: "强平线",
};

const lifecycleStateLabels: Record<string, string> = {
  active: "活跃",
  margin_call: "强平线",
  stopped: "已停止",
  created: "已创建",
};

const causalStepTypeLabels: Record<string, string> = {
  public_message: "公开消息",
  belief_shift: "信念变化",
  order_flow: "订单流",
  price_move: "价格变化",
};

const visibilityLabels: Record<string, string> = {
  public: "公开",
  control_only_view: "控制视图",
  agent_private_snapshot: "智能体私有快照",
  frontend_only: "前端审计视图",
};

const runtimeStateLabels: Record<string, string> = {
  AGENT_STEP: "智能体行动",
  MATCH_AND_CLEAR: "撮合清算",
  COMMIT_TICK: "提交节拍",
};

const accountFieldLabels: Record<string, string> = {
  cash: "现金",
  available_cash: "可用现金",
  positions: "持仓",
  available_shares: "可用股份",
  frozen_shares: "冻结股份",
  market_value: "市值",
  equity: "权益",
  risk_state: "风险状态",
};

const agentNameLabels: Record<string, string> = {
  mutual_fund_a: "公募甲",
  hot_money_a: "游资甲",
  retail_b: "散户乙",
  retail_cluster: "散户群体",
  market: "市场",
};

const symbolLabels: Record<string, string> = {
  demo_stock: "样例标的",
};

const sessionLabels: Record<string, string> = {
  sim_001: "演示会话一",
};

function App() {
  const [activeModule, setActiveModule] = usePersistentModule("CONFIG");
  const [session, setSession] = useState(seedState.session);
  const [market, setMarket] = useState<MarketSnapshot>(seedState.market);
  const [agents, setAgents] = useState<AgentSnapshot[]>(seedState.agents);
  const [events, setEvents] = useState<WebEventEnvelope[]>(seedState.events);
  const [selectedAgentId, setSelectedAgentId] = useState(seedState.agents[1]?.agent_id ?? "");
  const [connectionState, setConnectionState] = useState("DEMO_OFFLINE");
  const [pageState, setPageState] = useState<VisualState>("live");

  const selectedAgent = agents.find((agent) => agent.agent_id === selectedAgentId) ?? agents[0];

  return (
    <div className="app-shell">
      <TopNav activeModule={activeModule} onSelect={setActiveModule} status={session.status} />
      <main className="workspace">
        {activeModule === "CONFIG" && (
          <ConfigurationMatrix
            market={market}
            onCreated={(nextSession) => {
              setSession(nextSession);
              setConnectionState("SESSION_CREATED");
            }}
          />
        )}
        {activeModule === "LIVE" && (
          <LiveTelemetryCanvas
            session={session}
            market={market}
            agents={agents}
            graph={seedState.auditGraph}
            events={events}
            connectionState={connectionState}
            pageState={pageState}
            selectedAgentId={selectedAgentId}
            onSelectAgent={setSelectedAgentId}
            onStateChange={setPageState}
            onControl={(status) => {
              setSession((current) => ({ ...current, status }));
              setConnectionState(`CONTROL_${String(status).toUpperCase()}`);
              setPageState(status === "paused" ? "paused" : status === "running" ? "live" : "terminal");
            }}
          />
        )}
        {activeModule === "ENTITY" && (
          <EntityInspector
            agents={agents}
            selectedAgent={selectedAgent}
            chains={seedState.causalChains}
            onSelectAgent={setSelectedAgentId}
          />
        )}
        {activeModule === "CHRONOS" && (
          <ChronosScriptEditor
            session={session}
            currentTickId={session.current_tick_id}
            officialTrack={seedState.chronos.officialTrack}
            rumorTrack={seedState.chronos.rumorTrack}
            events={events}
          />
        )}
        {activeModule === "DOSSIER" && (
          <VulnerabilityDossier
            session={session}
            market={market}
            agents={agents}
            chains={seedState.causalChains}
            dossier={seedState.dossier}
          />
        )}
      </main>
    </div>
  );
}

type VisualState = "empty" | "loading" | "live" | "paused" | "recovering" | "error" | "terminal" | "replay";

function useState<T>(initialValue: T): [T, (next: T | ((current: T) => T)) => void] {
  return React.useState(initialValue);
}

function usePersistentModule(initialValue: ModuleKey) {
  const [value, setValue] = React.useState<ModuleKey>(() => {
    const stored = window.localStorage.getItem("ouroboros.activeModule");
    return modules.includes(stored as ModuleKey) ? (stored as ModuleKey) : initialValue;
  });

  const setPersistentValue = (next: ModuleKey) => {
    window.localStorage.setItem("ouroboros.activeModule", next);
    setValue(next);
  };

  return [value, setPersistentValue] as const;
}

import * as React from "react";

function TopNav({
  activeModule,
  onSelect,
  status,
}: {
  activeModule: ModuleKey;
  onSelect: (module: ModuleKey) => void;
  status: string;
}) {
  return (
    <header className="top-nav">
      <button className="brand-button" type="button" onClick={() => onSelect("CONFIG")}>
        Ouroboros
      </button>
      <nav className="module-nav" aria-label="主模块">
        {modules.map((module) => (
          <button
            className={module === activeModule ? "module-link active" : "module-link"}
            key={module}
            type="button"
            onClick={() => onSelect(module)}
          >
            {moduleLabels[module]}
          </button>
        ))}
      </nav>
      <div className="status-strip">
        <span>会话状态</span>
        <strong>{labelFrom(sessionStatusLabels, status)}</strong>
      </div>
    </header>
  );
}

function ConfigurationMatrix({
  market,
  onCreated,
}: {
  market: MarketSnapshot;
  onCreated: (session: typeof seedState.session) => void;
}) {
  const [form, setForm] = useState({
    ticker: market.symbol,
    scenarioId: "样例甲股压力测试",
    chronosAnchor: "2024-01-02 09:30:00 +08:00",
    startTick: "2024-01-02 09:30:00 +08:00",
    endTick: "2024-01-02 15:00:00 +08:00",
    tickInterval: "5 分钟",
  });
  const [profiles, setProfiles] = useState(seedState.agentProfiles);
  const hasLocalProfileDraft = JSON.stringify(profiles) !== JSON.stringify(seedState.agentProfiles);

  function updateField(field: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function adjustProfile(index: number, field: keyof (typeof profiles)[number], delta: number) {
    setProfiles((current) =>
      current.map((profile, profileIndex) => {
        if (profileIndex !== index) return profile;
        const currentValue = Number(profile[field]);
        return { ...profile, [field]: Math.max(0, currentValue + delta) };
      }),
    );
  }

  return (
    <section className="page-grid configuration-page">
      <header className="masthead">
        <div>
          <p className="eyebrow">沙盘初始化控制台</p>
          <h1>[OUROBOROS // 新建推演]</h1>
        </div>
        <div className="market-block">
          <span>标的 {displaySymbol(market.symbol)}</span>
          <strong>{market.last_price.toFixed(2)}</strong>
        </div>
      </header>

      <section className="config-columns">
        <div className="panel form-panel">
          <h2>标的与环境</h2>
          {[
            ["标的代码", "ticker"],
            ["场景编号", "scenarioId"],
            ["时间锚点", "chronosAnchor"],
            ["起始节拍", "startTick"],
            ["结束节拍", "endTick"],
            ["节拍间隔", "tickInterval"],
          ].map(([label, field]) => (
            <label className="field-row" key={field}>
              <span>{label}</span>
              <input value={form[field as keyof typeof form]} onChange={(event) => updateField(field as keyof typeof form, event.target.value)} />
            </label>
          ))}
        </div>

        <div className="panel agent-balance">
          <h2>智能体配平</h2>
          <div className="profile-grid">
            {profiles.map((profile, index) => (
              <article className="profile-cell" key={profile.label}>
                <h3>{profile.label}</h3>
                <Radar values={[profile.count, profile.capitalWeight, profile.infoSensitivity, profile.riskAversion]} />
                {[
                  ["智能体数量", "count"],
                  ["资金权重", "capitalWeight"],
                  ["信息敏感度", "infoSensitivity"],
                  ["风险厌恶度", "riskAversion"],
                ].map(([label, field]) => (
                  <Stepper
                    key={field}
                    label={label}
                    value={Number(profile[field as keyof typeof profile])}
                    onMinus={() => adjustProfile(index, field as keyof typeof profile, -1)}
                    onPlus={() => adjustProfile(index, field as keyof typeof profile, 1)}
                  />
                ))}
              </article>
            ))}
          </div>
        </div>
      </section>

      {hasLocalProfileDraft && (
        <div className="local-profile-warning" role="status">
          LOCAL PROFILE PREVIEW ONLY // SUBMIT USES agent_profile_set=default_24
        </div>
      )}

      <button
        className="primary-command"
        type="button"
        onClick={() =>
          onCreated({
            ...seedState.session,
            symbol: form.ticker,
            status: "created",
            current_tick_id: form.startTick,
          })
        }
      >
        [启动推演序列]
      </button>
    </section>
  );
}

function Stepper({ label, value, onMinus, onPlus }: { label: string; value: number; onMinus: () => void; onPlus: () => void }) {
  return (
    <div className="stepper-row">
      <span>{label}</span>
      <div className="stepper-control">
        <button type="button" onClick={onMinus} aria-label={`${label}减少`}>
          -
        </button>
        <output>{value}</output>
        <button type="button" onClick={onPlus} aria-label={`${label}增加`}>
          +
        </button>
      </div>
    </div>
  );
}

function Radar({ values }: { values: number[] }) {
  const max = Math.max(...values, 10);
  const points = values
    .map((value, index) => {
      const angle = -Math.PI / 2 + (index * Math.PI * 2) / values.length;
      const radius = 34 * (value / max);
      return `${50 + Math.cos(angle) * radius},${50 + Math.sin(angle) * radius}`;
    })
    .join(" ");

  return (
    <svg className="radar" viewBox="0 0 100 100" role="img" aria-label="智能体参数雷达图">
      <polygon points="50,16 84,50 50,84 16,50" fill="none" stroke="currentColor" strokeWidth="1" />
      <polygon points="50,28 72,50 50,72 28,50" fill="none" stroke="currentColor" strokeWidth="1" />
      <polyline points={`${points} ${points.split(" ")[0]}`} fill="none" stroke="#002fa7" strokeWidth="1.5" />
    </svg>
  );
}

function LiveTelemetryCanvas({
  session,
  market,
  agents,
  graph,
  events,
  connectionState,
  pageState,
  selectedAgentId,
  onSelectAgent,
  onStateChange,
  onControl,
}: {
  session: typeof seedState.session;
  market: MarketSnapshot;
  agents: AgentSnapshot[];
  graph: typeof seedState.auditGraph;
  events: WebEventEnvelope[];
  connectionState: string;
  pageState: VisualState;
  selectedAgentId: string;
  onSelectAgent: (agentId: string) => void;
  onStateChange: (state: VisualState) => void;
  onControl: (status: SessionStatus) => void;
}) {
  const [hoveredAgentId, setHoveredAgentId] = useState<string | null>(null);
  const [selectedReasonRef, setSelectedReasonRef] = useState<string | null>(null);
  const [edgeMode, setEdgeMode] = useState<"current" | "selected" | "strong">("current");
  const [scrubIndex, setScrubIndex] = useState(seedState.chronos.ticks.indexOf(session.current_tick_id));
  const feedEvents = events.filter((event) =>
    ["runtime.tick_state", "market.tape_alert", "forum.post", "system.error"].includes(event.type),
  );
  const safeScrubIndex = Math.max(0, scrubIndex);
  const displayTick = seedState.chronos.ticks[safeScrubIndex] ?? session.current_tick_id;
  const stateLabel = pageState === "recovering" ? "RECOVERING SNAPSHOT" : pageState === "replay" ? "REPLAY TICK" : labelFrom(sessionStatusLabels, session.status);
  const selectedAgent = agents.find((agent) => agent.agent_id === selectedAgentId);
  const selectedNode = graph.nodes.find((node) => node.agent_id === selectedAgentId);
  const selectedEdges = graph.edges.filter((edge) => edge.source === selectedAgentId || edge.target === selectedAgentId);

  return (
    <section className={`live-page state-${pageState}`}>
      <header className="terminal-header live-terminal-header">
        <span>Ouroboros 实时推演</span>
        <span>会话 {displaySession(session.session_id)}</span>
        <span>节拍 {formatTick(displayTick)}</span>
        <span>{stateLabel}</span>
        <span>{labelFrom(connectionLabels, connectionState)}</span>
        <div className="control-buttons">
          <IconButton label="开始" onClick={() => onControl("running")}>
            <Play size={16} />
          </IconButton>
          <IconButton label="暂停" onClick={() => onControl("paused")}>
            <Square size={16} />
          </IconButton>
          <IconButton label="单步推进" onClick={() => onControl("running")}>
            <StepForward size={16} />
          </IconButton>
          <IconButton label="恢复快照" onClick={() => onStateChange("recovering")}>
            <RotateCcw size={16} />
          </IconButton>
        </div>
      </header>
      <div className="live-columns">
        <aside className="chronos-feed">
          <h2>时间轴事件流</h2>
          {feedEvents.map((event) => (
            <article
              className={event.trace_id === selectedReasonRef || readPayloadField(event, "post_id", "") === selectedReasonRef ? "sync-highlight" : ""}
              key={`${event.seq}-${event.type}`}
            >
              <time>{formatTick(event.tick_id)}</time>
              <strong>{labelFrom(eventTypeLabels, event.type)}</strong>
              <p>{eventText(event)}</p>
            </article>
          ))}
        </aside>
        <section className="canvas-stack">
          <Topology
            agents={agents}
            graph={graph}
            edgeMode={edgeMode}
            hoveredAgentId={hoveredAgentId}
            selectedAgentId={selectedAgentId}
            selectedReasonRef={selectedReasonRef}
            tickId={displayTick}
            onHoverAgent={setHoveredAgentId}
            onSelectAgent={onSelectAgent}
            onSelectReason={setSelectedReasonRef}
            onEdgeModeChange={setEdgeMode}
          />
          <TickScrubber
            currentIndex={safeScrubIndex}
            ticks={seedState.chronos.ticks}
            onChange={(index) => {
              setScrubIndex(index);
              onStateChange(index === seedState.chronos.ticks.indexOf(session.current_tick_id) ? "live" : "replay");
            }}
          />
          <MarketCurves market={market} events={events} />
        </section>
        <aside className="order-book inspector-book">
          <section className="agent-inspector">
            <h2>Inspector</h2>
            {selectedAgent && selectedNode ? (
              <div className="inspector-grid">
                <span>agent_id</span>
                <strong>{selectedAgent.agent_id}</strong>
                <span>type</span>
                <strong>{labelFrom(agentTypeLabels, selectedAgent.agent_type)}</strong>
                <span>risk</span>
                <strong>{labelFrom(riskStateLabels, selectedAgent.risk_state)}</strong>
                <span>belief</span>
                <strong>{selectedNode.belief_score.toFixed(2)}</strong>
                <span>position</span>
                <strong>{formatPercent(positionExposure(selectedNode, graph.nodes))}</strong>
              </div>
            ) : (
              <EmptyState label="NO AGENT SELECTED" />
            )}
            <div className="chain-list">
              {selectedEdges.length ? (
                selectedEdges.map((edge) => (
                  <button type="button" key={edge.reason_ref} onClick={() => setSelectedReasonRef(edge.reason_ref)}>
                    {edge.reason_ref} W:{edge.weight.toFixed(2)}
                  </button>
                ))
              ) : (
                <span>NO PUBLIC CAUSAL CHAIN</span>
              )}
            </div>
          </section>
          <h2>盘口</h2>
          <BookSide title="卖盘" rows={market.level2.asks} side="sell" />
          <BookSide title="买盘" rows={market.level2.bids} side="buy" />
        </aside>
      </div>
    </section>
  );
}

function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button className="icon-button" type="button" onClick={onClick} title={label} aria-label={label}>
      {children}
    </button>
  );
}

function Topology({
  agents,
  graph,
  edgeMode,
  hoveredAgentId,
  selectedAgentId,
  selectedReasonRef,
  tickId,
  onHoverAgent,
  onSelectAgent,
  onSelectReason,
  onEdgeModeChange,
}: {
  agents: AgentSnapshot[];
  graph: typeof seedState.auditGraph;
  edgeMode: "current" | "selected" | "strong";
  hoveredAgentId: string | null;
  selectedAgentId: string;
  selectedReasonRef: string | null;
  tickId: string;
  onHoverAgent: (agentId: string | null) => void;
  onSelectAgent: (agentId: string) => void;
  onSelectReason: (reasonRef: string | null) => void;
  onEdgeModeChange: (mode: "current" | "selected" | "strong") => void;
}) {
  const graphNodes = graph.nodes.length ? graph.nodes : agents.map(agentToGraphNode);
  const nodes = graphNodes.map((node, index) => {
    const point = deterministicNodePoint(index, graphNodes.length);
    return { ...node, ...point };
  });
  const nodeById = new Map(nodes.map((node) => [node.agent_id, node]));
  const visibleEdges = pruneGraphEdges(graph.edges, selectedAgentId, edgeMode);
  const spotlightIds = hoveredAgentId
    ? new Set([
        hoveredAgentId,
        ...graph.edges.filter((edge) => edge.source === hoveredAgentId || edge.target === hoveredAgentId).flatMap((edge) => [edge.source, edge.target]),
      ])
    : null;

  return (
    <div className="topology panel">
      <div className="section-title">
        <Network size={16} />
        <span>共识感染画布</span>
        <div className="canvas-tools">
          <button type="button" onClick={() => onEdgeModeChange("current")}>
            <Eye size={14} /> 当前 Tick
          </button>
          <button type="button" onClick={() => onEdgeModeChange("selected")}>
            <Crosshair size={14} /> 选中链路
          </button>
          <button type="button" onClick={() => onEdgeModeChange("strong")}>
            <Network size={14} /> 高影响
          </button>
          <button type="button" onClick={() => onSelectReason(null)}>
            <RotateCcw size={14} /> 重置视图
          </button>
        </div>
      </div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="共识感染拓扑图">
        <defs>
          <pattern id="engineering-grid" width="10" height="10" patternUnits="userSpaceOnUse">
            <path d="M 10 0 L 0 0 0 10" fill="none" stroke="#000" strokeOpacity="0.05" strokeWidth="0.5" />
          </pattern>
          <marker id="sharp-arrow" viewBox="0 0 6 6" refX="5.5" refY="3" markerWidth="4" markerHeight="4" orient="auto">
            <path d="M 0 0 L 6 3 L 0 6 Z" fill="#000" />
          </marker>
          <clipPath id="belief-top-circle">
            <rect x="-12" y="-12" width="24" height="12" />
          </clipPath>
        </defs>
        <rect x="0" y="0" width="100" height="100" fill="url(#engineering-grid)" />
        <text x="2" y="5" fontSize="2.3" fill="#000">
          X:-240.50 Y:112.00 // SCALE 1:1
        </text>
        <text x="66" y="96" fontSize="2.3" fill="#000">
          TICK {formatTick(tickId)}
        </text>
        {visibleEdges.map((edge, index) => {
          const source = nodeById.get(edge.source);
          const target = nodeById.get(edge.target);
          if (!source || !target) return null;
          const isDimmed = spotlightIds ? !spotlightIds.has(edge.source) && !spotlightIds.has(edge.target) : false;
          const isSelected = edge.reason_ref === selectedReasonRef;
          return (
            <path
              className={isDimmed ? "graph-dimmed" : ""}
              key={`${edge.source}-${edge.target}-${edge.reason_ref}`}
              d={bezierPath(source, target)}
              fill="none"
              markerEnd="url(#sharp-arrow)"
              onClick={() => onSelectReason(edge.reason_ref)}
              stroke={isSelected || index % 2 === 0 ? "#002fa7" : "#000"}
              strokeDasharray={edge.weight < 0.3 ? "1 2" : index % 3 === 0 ? "4 3" : undefined}
              strokeWidth="0.5"
            >
              <title>{edge.public_reason} W:{edge.weight.toFixed(2)}</title>
            </path>
          );
        })}
        {nodes.map((node) => (
          <g
            className={spotlightIds && !spotlightIds.has(node.agent_id) ? "graph-dimmed" : ""}
            key={node.agent_id}
            onClick={() => onSelectAgent(node.agent_id)}
            onMouseEnter={() => onHoverAgent(node.agent_id)}
            onMouseLeave={() => onHoverAgent(null)}
          >
            {node.agent_id === selectedAgentId && <rect x={node.x - 6} y={node.y - 6} width="12" height="12" fill="none" stroke="#000" strokeDasharray="1.4 1.4" strokeWidth="0.5" />}
            <NodeGlyph node={node} allNodes={graphNodes} shape={node.agent_id === "retail_b" ? "square" : "circle"} />
            <line x1={node.x + 4.8} y1={node.y} x2={node.x + 11} y2={node.y} stroke="#000" strokeWidth="0.35" />
            <text x={node.x + 11.5} y={node.y + 0.8} fontSize="2.2" fill="#000">
              [{formatAgentCode(node.agent_id)}] C:{node.belief_score.toFixed(2)} P:{formatPercent(positionExposure(node, graphNodes))}
            </text>
            <title>
              {node.agent_id} / {labelFrom(agentTypeLabels, node.agent_type)} / {labelFrom(riskStateLabels, node.risk_state)} / belief {node.belief_score.toFixed(2)} / position {formatPercent(positionExposure(node, graphNodes))}
            </title>
          </g>
        ))}
      </svg>
    </div>
  );
}

function NodeGlyph({
  node,
  allNodes,
  shape,
}: {
  node: AuditGraphNode & { x: number; y: number };
  allNodes: AuditGraphNode[];
  shape: "circle" | "square";
}) {
  const fillHeight = Math.max(0, Math.min(1, Math.abs(node.belief_score - 0.5) * 2)) * 5;
  const beliefFill = node.belief_score > 0.6 ? "#002fa7" : node.belief_score < 0.4 ? "#000" : "#fff";
  const exposure = positionExposure(node, allNodes);
  if (shape === "square") {
    return (
      <>
        <rect x={node.x - 4.2} y={node.y - 4.2} width="8.4" height="8.4" fill="#fff" stroke={node.risk_state === "warning" ? "#002fa7" : "#000"} strokeWidth="0.6" />
        <rect x={node.x - 4.2} y={node.y - 4.2} width="8.4" height={fillHeight} fill={beliefFill} />
        <line x1={node.x - 3.4} y1={node.y + 3.5} x2={node.x - 3.4 + exposure * 6.8} y2={node.y + 3.5} stroke="#000" strokeWidth="0.7" />
      </>
    );
  }
  return (
    <>
      <circle cx={node.x} cy={node.y} r="4.4" fill="#fff" stroke={node.risk_state === "warning" ? "#002fa7" : "#000"} strokeWidth="0.6" />
      <g transform={`translate(${node.x} ${node.y})`} clipPath="url(#belief-top-circle)">
        <circle cx="0" cy="0" r="4.4" fill={beliefFill} />
      </g>
      <line x1={node.x - 3.3} y1={node.y + 3.5} x2={node.x - 3.3 + exposure * 6.6} y2={node.y + 3.5} stroke="#000" strokeWidth="0.7" />
    </>
  );
}

function TickScrubber({ ticks, currentIndex, onChange }: { ticks: string[]; currentIndex: number; onChange: (index: number) => void }) {
  return (
    <div className="tick-scrubber">
      <input
        aria-label="Tick 时间刮擦器"
        max={Math.max(ticks.length - 1, 0)}
        min={0}
        onChange={(event) => onChange(Number(event.target.value))}
        step={1}
        type="range"
        value={currentIndex}
      />
      <div className="tick-marks">
        {ticks.map((tick, index) => (
          <span className={index === currentIndex ? "active" : ""} key={tick}>
            T{index}
          </span>
        ))}
      </div>
    </div>
  );
}

function MarketCurves({ market, events }: { market: MarketSnapshot; events: WebEventEnvelope[] }) {
  const priceEvents = events.filter((event) => event.type === "market.price").slice(-18);
  const prices = priceEvents.length ? priceEvents.map((event) => Number(readPayloadField(event, "last_price", market.last_price))) : seedState.priceSeries;
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const points = prices
    .map((price, index) => {
      const x = (index / Math.max(prices.length - 1, 1)) * 96 + 2;
      const y = 88 - ((price - min) / Math.max(max - min, 0.01)) * 76;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div className="market-curves panel">
      <div className="section-title">
        <Activity size={16} />
        <span>价格 / 共识曲线</span>
      </div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none">
        <polyline points={points} fill="none" stroke="#002fa7" strokeWidth="1.6" />
        <line x1="2" y1="52" x2="98" y2="44" stroke="#000" strokeWidth="0.8" />
        <text x="3" y="12" fontSize="4" fill="#000">
          高点 {max.toFixed(2)}
        </text>
        <text x="3" y="94" fontSize="4" fill="#000">
          低点 {min.toFixed(2)}
        </text>
        <text x="72" y="14" fontSize="4" fill="#002fa7">
          最新 {market.last_price.toFixed(2)}
        </text>
      </svg>
    </div>
  );
}

function BookSide({ title, rows, side }: { title: string; rows: [string, number][]; side: "buy" | "sell" }) {
  return (
    <section>
      <h3>{title}</h3>
      {rows.map(([price, volume]) => (
        <div className={`book-row ${side}`} key={`${side}-${price}`}>
          <span>{price}</span>
          <span>{volume.toLocaleString("en-US")}</span>
        </div>
      ))}
    </section>
  );
}

function EmptyState({ label }: { label: string }) {
  return <div className="empty-state">{label}</div>;
}

function EntityInspector({
  agents,
  selectedAgent,
  chains,
  onSelectAgent,
}: {
  agents: AgentSnapshot[];
  selectedAgent: AgentSnapshot;
  chains: CausalChain[];
  onSelectAgent: (agentId: string) => void;
}) {
  return (
    <section className="entity-page">
      <header className="terminal-header">
        <span>智能体解剖室</span>
        <span>[{displayAgentName(selectedAgent.agent_id)}]</span>
      </header>
      <div className="entity-layout">
        <aside className="roster">
          {agents.map((agent) => (
            <button
              className={agent.agent_id === selectedAgent.agent_id ? "active" : ""}
              type="button"
              key={agent.agent_id}
              onClick={() => onSelectAgent(agent.agent_id)}
            >
              <span>[{displayAgentName(agent.agent_id)}]</span>
              {agent.risk_state !== "normal" && <mark>{labelFrom(riskStateLabels, agent.risk_state)}</mark>}
            </button>
          ))}
        </aside>
        <section className="quadrants">
          <div className="panel account-table">
            <h2>资产表</h2>
            {[
              ["cash", selectedAgent.cash],
              ["available_cash", selectedAgent.available_cash],
              ["positions", Object.values(selectedAgent.positions).join(" / ")],
              ["available_shares", Object.values(selectedAgent.available_shares).join(" / ")],
              ["frozen_shares", Object.values(selectedAgent.frozen_shares).join(" / ")],
              ["market_value", selectedAgent.market_value],
              ["equity", selectedAgent.equity],
              ["risk_state", selectedAgent.risk_state],
            ].map(([label, value]) => (
              <div className="table-line" key={label}>
                <span>{labelFrom(accountFieldLabels, String(label))}</span>
                <strong>{formatAccountValue(String(label), value)}</strong>
              </div>
            ))}
          </div>
          <div className="panel belief-track">
            <h2>信念轨迹</h2>
            <svg viewBox="0 0 100 100" preserveAspectRatio="none">
              <polyline points="3,76 18,68 34,62 50,39 66,48 82,28 97,35" fill="none" stroke="#002fa7" strokeWidth="1.4" />
              <circle cx="50" cy="39" r="2" fill="#002fa7" />
              <text x="53" y="37" fontSize="4">强平线</text>
            </svg>
          </div>
          <div className="panel audit-room">
            <h2>脱敏审计室</h2>
            {chains.map((chain) => (
              <article key={chain.chain_id}>
                <h3>{chain.title}</h3>
                <p>{chain.summary}</p>
                {chain.steps.slice(0, 4).map((step) => (
                  <div className="audit-step" key={step.step_id}>
                    <time>{formatTick(step.tick_id)}</time>
                    <strong>{step.label}</strong>
                    <span>{step.public_text}</span>
                  </div>
                ))}
              </article>
            ))}
          </div>
        </section>
      </div>
    </section>
  );
}

function ChronosScriptEditor({
  session,
  currentTickId,
  officialTrack,
  rumorTrack,
}: {
  session: typeof seedState.session;
  currentTickId: string;
  officialTrack: typeof seedState.chronos.officialTrack;
  rumorTrack: typeof seedState.chronos.rumorTrack;
  events: WebEventEnvelope[];
}) {
  return (
    <section className="chronos-page">
      <header className="terminal-header">
        <span>时间轴剧本管理</span>
        <span>READ ONLY TIMELINE</span>
        <span>{displaySession(session.session_id)}</span>
        <span>{formatTick(currentTickId)}</span>
      </header>
      <div className="timeline">
        {seedState.chronos.ticks.map((tick) => (
          <span className={tick === currentTickId ? "current" : tick > currentTickId ? "future" : ""} key={tick} title={formatTick(tick)} />
        ))}
      </div>
      <div className="chronos-tracks">
        <section className="official-track">
          <h2>官方事实轨</h2>
          {officialTrack.map((item) => (
            <article key={item.id}>
              <time>{formatTick(item.tick_id)}</time>
              <h3>{item.title}</h3>
              <p>{item.public_text}</p>
            </article>
          ))}
        </section>
        <section className="rumor-track">
          <h2>公开传闻轨</h2>
          {rumorTrack.map((item) => (
            <article key={item.id}>
              <time>{formatTick(item.tick_id)}</time>
              <p>{item.public_text}</p>
            </article>
          ))}
        </section>
      </div>
    </section>
  );
}

function VulnerabilityDossier({
  session,
  market,
  agents,
  chains,
  dossier,
}: {
  session: typeof seedState.session;
  market: MarketSnapshot;
  agents: AgentSnapshot[];
  chains: CausalChain[];
  dossier: typeof seedState.dossier;
}) {
  const rankedAgents = [...agents].sort((a, b) => b.equity - a.equity).slice(0, 6);
  const collapseProbability = typeof dossier.collapseProbability === "number" ? `${dossier.collapseProbability}%` : "N/A";

  return (
    <section className="dossier-page">
      <header className="dossier-header">
        <h1>崩塌概率：{collapseProbability}</h1>
        <div>
          <span>会话 {displaySession(session.session_id)}</span>
          <span>标的 {displaySymbol(market.symbol)}</span>
          <span>节拍 {formatTick(session.current_tick_id)}</span>
          <span>生成 {formatTick(dossier.generatedAt)}</span>
        </div>
      </header>
      <div className="dossier-columns">
        <section>
          <h2>概述与定性</h2>
          <p>{dossier.summary}</p>
          <p>{dossier.finding}</p>
        </section>
        <section>
          <h2>图表证据</h2>
          <DossierPath chains={chains} />
        </section>
        <section>
          <h2>虚拟龙虎榜 / 附录</h2>
          <table>
            <thead>
              <tr>
                <th>智能体</th>
                <th>类型</th>
                <th>权益</th>
                <th>风险</th>
              </tr>
            </thead>
            <tbody>
              {rankedAgents.map((agent) => (
                <tr key={agent.agent_id}>
                  <td>{displayAgentName(agent.agent_id)}</td>
                  <td>{labelFrom(agentTypeLabels, agent.agent_type)}</td>
                  <td>{Math.round(agent.equity).toLocaleString("en-US")}</td>
                  <td>{labelFrom(riskStateLabels, agent.risk_state)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </section>
  );
}

function DossierPath({ chains }: { chains: CausalChain[] }) {
  const steps = chains[0]?.steps ?? [];
  return (
    <svg className="dossier-path" viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="因果路径">
      {steps.map((step, index) => (
        <g key={step.step_id}>
          <rect x={6 + index * 22} y={22 + (index % 2) * 24} width="16" height="10" fill="#fff" stroke="#000" />
          <text x={7 + index * 22} y={29 + (index % 2) * 24} fontSize="3">
            {labelFrom(causalStepTypeLabels, step.step_type)}
          </text>
          {index < steps.length - 1 && (
            <path
              d={`M ${22 + index * 22} ${27 + (index % 2) * 24} C ${29 + index * 22} ${8 + (index % 2) * 24}, ${35 + index * 22} ${66 - (index % 2) * 24}, ${50 + index * 22} ${27 + ((index + 1) % 2) * 24}`}
              fill="none"
              stroke={index === 1 ? "#002fa7" : "#000"}
              strokeWidth="0.9"
            />
          )}
        </g>
      ))}
    </svg>
  );
}

function eventText(event: WebEventEnvelope) {
  const publicText = readPayloadField(event, "public_text", "");
  if (publicText) return String(publicText);
  const text = readPayloadField(event, "text", "");
  if (text) return String(text);
  const message = readPayloadField(event, "message", "");
  if (message) return String(message);
  const state = readPayloadField(event, "state", "");
  if (state) return labelFrom(runtimeStateLabels, String(state));
  return labelFrom(visibilityLabels, event.visibility);
}

function labelFrom(labels: Record<string, string>, value: string | undefined): string {
  if (!value) return "";
  return labels[value] ?? value;
}

function displayAgentName(agentId: string): string {
  return labelFrom(agentNameLabels, agentId);
}

function formatAgentCode(agentId: string): string {
  const knownIndex = seedState.agents.findIndex((agent) => agent.agent_id === agentId);
  if (knownIndex >= 0) return `AGT-${String(knownIndex + 1).padStart(2, "0")}`;
  const hash = [...agentId].reduce((total, char) => total + char.charCodeAt(0), 0);
  return `AGT-${String((hash % 99) + 1).padStart(2, "0")}`;
}

function displaySymbol(symbol: string): string {
  return labelFrom(symbolLabels, symbol);
}

function displaySession(sessionId: string): string {
  return labelFrom(sessionLabels, sessionId);
}

function formatTick(value: string): string {
  return value.replace("T", " ").replace("+08:00", "");
}

function formatAccountValue(label: string, value: unknown): string {
  if (typeof value === "number") return value.toLocaleString("en-US");
  if (label === "risk_state" && typeof value === "string") return labelFrom(riskStateLabels, value);
  return String(value);
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function agentToGraphNode(agent: AgentSnapshot): AuditGraphNode {
  const maxEquity = Math.max(...seedState.agents.map((item) => item.equity), 1);
  return {
    agent_id: agent.agent_id,
    agent_type: agent.agent_type,
    belief_score: Math.max(0, Math.min(1, agent.equity / maxEquity)),
    position_value: agent.position_value,
    risk_state: agent.risk_state,
  };
}

function deterministicNodePoint(index: number, total: number) {
  const radiusX = 33;
  const radiusY = 26;
  const angle = -Math.PI / 2 + (index * Math.PI * 2) / Math.max(total, 1);
  return {
    x: 50 + Math.cos(angle) * radiusX,
    y: 50 + Math.sin(angle) * radiusY,
  };
}

function pruneGraphEdges(edges: AuditGraphEdge[], selectedAgentId: string, edgeMode: "current" | "selected" | "strong") {
  const selectedEdges = edges.filter((edge) => edge.source === selectedAgentId || edge.target === selectedAgentId);
  const strongEdges = edges.filter((edge) => edge.weight >= 0.3);
  const source = edgeMode === "selected" ? selectedEdges : edgeMode === "strong" ? strongEdges : strongEdges.length ? strongEdges : edges;
  return [...source].sort((a, b) => b.weight - a.weight).slice(0, 48);
}

function positionExposure(node: AuditGraphNode, allNodes: AuditGraphNode[]) {
  const maxPosition = Math.max(...allNodes.map((item) => item.position_value), 1);
  return Math.max(0, Math.min(1, node.position_value / maxPosition));
}

function bezierPath(source: { x: number; y: number }, target: { x: number; y: number }) {
  const dx = target.x - source.x;
  return `M ${source.x} ${source.y} C ${source.x + dx * 0.45} ${source.y}, ${target.x - dx * 0.45} ${target.y}, ${target.x} ${target.y}`;
}

function readPayloadField<TFallback extends string | number>(
  event: WebEventEnvelope,
  field: string,
  fallback: TFallback,
): string | number | TFallback {
  const payload = event.payload as unknown;
  if (!payload || typeof payload !== "object") return fallback;
  const value = (payload as Record<string, unknown>)[field];
  return typeof value === "string" || typeof value === "number" ? value : fallback;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
