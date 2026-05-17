import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { Activity, Network, Play, Square, StepForward } from "lucide-react";
import "./styles/global.css";
import { seedState } from "./data/seed";
import type { AgentSnapshot, CausalChain, MarketSnapshot, SessionStatus, WebEventEnvelope } from "./types/webApi";

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
            events={events}
            connectionState={connectionState}
            onControl={(status) => {
              setSession((current) => ({ ...current, status }));
              setConnectionState(`CONTROL_${String(status).toUpperCase()}`);
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
  events,
  connectionState,
  onControl,
}: {
  session: typeof seedState.session;
  market: MarketSnapshot;
  agents: AgentSnapshot[];
  events: WebEventEnvelope[];
  connectionState: string;
  onControl: (status: SessionStatus) => void;
}) {
  const feedEvents = events.filter((event) =>
    ["runtime.tick_state", "market.tape_alert", "forum.post", "system.error"].includes(event.type),
  );

  return (
    <section className="live-page">
      <header className="terminal-header">
        <span>Ouroboros 实时推演</span>
        <span>会话 {displaySession(session.session_id)}</span>
        <span>节拍 {formatTick(session.current_tick_id)}</span>
        <span>{labelFrom(sessionStatusLabels, session.status)}</span>
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
        </div>
      </header>
      <div className="live-columns">
        <aside className="chronos-feed">
          <h2>时间轴事件流</h2>
          {feedEvents.map((event) => (
            <article key={`${event.seq}-${event.type}`}>
              <time>{formatTick(event.tick_id)}</time>
              <strong>{labelFrom(eventTypeLabels, event.type)}</strong>
              <p>{eventText(event)}</p>
            </article>
          ))}
        </aside>
        <section className="canvas-stack">
          <Topology agents={agents} />
          <MarketCurves market={market} events={events} />
        </section>
        <aside className="order-book">
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

function Topology({ agents }: { agents: AgentSnapshot[] }) {
  const nodes = agents.slice(0, 8).map((agent, index) => {
    const x = 12 + (index % 4) * 26;
    const y = 25 + Math.floor(index / 4) * 38;
    return { ...agent, x, y };
  });

  return (
    <div className="topology panel">
      <div className="section-title">
        <Network size={16} />
        <span>共识感染画布</span>
      </div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none">
        {nodes.slice(0, -1).map((node, index) => (
          <path
            key={`${node.agent_id}-${nodes[index + 1].agent_id}`}
            d={`M ${node.x} ${node.y} C ${node.x + 12} ${node.y - 16}, ${nodes[index + 1].x - 12} ${nodes[index + 1].y + 16}, ${nodes[index + 1].x} ${nodes[index + 1].y}`}
            fill="none"
            stroke={index % 2 ? "#000" : "#002fa7"}
            strokeDasharray={index % 3 === 0 ? "5 3" : undefined}
            strokeWidth="0.6"
          />
        ))}
        {nodes.map((node) => (
          <g key={node.agent_id}>
            <circle
              cx={node.x}
              cy={node.y}
              r="3.8"
              fill={node.risk_state === "margin_call" ? "#002fa7" : "#fff"}
              stroke={node.risk_state === "warning" ? "#002fa7" : "#000"}
              strokeWidth="0.8"
            />
            <line x1={node.x + 4} y1={node.y} x2={node.x + 10} y2={node.y - 5} stroke="#000" strokeWidth="0.4" />
            <text x={node.x + 11} y={node.y - 6} fontSize="2.6" fill="#000">
              [{displayAgentName(node.agent_id)}] {labelFrom(lifecycleStateLabels, node.lifecycle_state)}
            </text>
          </g>
        ))}
      </svg>
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

  return (
    <section className="dossier-page">
      <header className="dossier-header">
        <h1>崩塌概率：{dossier.collapseProbability}%</h1>
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
