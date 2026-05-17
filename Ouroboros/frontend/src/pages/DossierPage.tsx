import { useEffect, useMemo, useState } from "react";
import { DossierPath } from "../components/dossier/DossierPath";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingSkeleton } from "../components/common/LoadingSkeleton";
import {
  agentNameLabels,
  agentTypeLabels,
  labelFrom,
  riskStateLabels,
} from "../i18n/labels";
import { useEvents, useSession, useSnapshot } from "../state";
import { deriveAccountSnapshots, deriveCausalChains } from "../utils/derive";
import { displaySession, displaySymbol, formatTick } from "../utils/format";
import type {
  AgentAccountSnapshotPayload,
  AgentSummary,
  AuditCausalChainPayload,
  MarketEndOfDayPayload,
  ServerEventEnvelope,
  SessionData,
  SnapshotData,
} from "../types/api";

type ReportAgent = Pick<
  AgentSummary,
  "agent_id" | "agent_type" | "risk_state" | "equity" | "position_value"
> &
  Partial<Pick<AgentAccountSnapshotPayload, "cash" | "market_value">>;

interface ReportSnapshot {
  session: SessionData | null;
  snapshot: SnapshotData | null;
  events: ServerEventEnvelope[];
  generatedAt: string;
}

const DISPLAY_EVENT_TYPES = new Set([
  "runtime.tick_state",
  "runtime.agent_lifecycle",
  "market.price",
  "market.tape_alert",
  "market.end_of_day",
  "forum.post",
  "agent.account_snapshot",
  "audit.graph",
  "audit.causal_chain",
  "system.error",
]);

function pickLatestEndOfDay(events: ReadonlyArray<ServerEventEnvelope>): MarketEndOfDayPayload | null {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    if (events[i].type === "market.end_of_day") {
      return events[i].payload as MarketEndOfDayPayload;
    }
  }
  return null;
}

function readCollapseProbability(snapshotData: SnapshotData | null, sessionData: SessionData | null): string {
  const containers: unknown[] = [snapshotData, sessionData];
  for (const container of containers) {
    if (!container || typeof container !== "object") continue;
    const value = (container as Record<string, unknown>).collapse_probability;
    if (typeof value === "number" && Number.isFinite(value)) {
      return `${(value * 100).toFixed(1)}%`;
    }
  }
  return "N/A";
}

function eventReference(evt: ServerEventEnvelope): string {
  return `#${evt.seq} ${evt.type} / ${evt.tick_id}`;
}

function buildReportAgents(
  snapshotData: SnapshotData | null,
  reportEvents: ReadonlyArray<ServerEventEnvelope>,
): ReportAgent[] {
  const byAgent = new Map<string, ReportAgent>();
  for (const agent of snapshotData?.agents ?? []) {
    byAgent.set(agent.agent_id, {
      agent_id: agent.agent_id,
      agent_type: agent.agent_type,
      risk_state: agent.risk_state,
      equity: agent.equity,
      position_value: agent.position_value,
    });
  }
  for (const account of deriveAccountSnapshots(reportEvents).values()) {
    byAgent.set(account.agent_id, {
      ...byAgent.get(account.agent_id),
      agent_id: account.agent_id,
      agent_type: account.agent_type,
      risk_state: account.risk_state,
      equity: account.equity,
      position_value: account.market_value,
      cash: account.cash,
      market_value: account.market_value,
    });
  }
  return Array.from(byAgent.values());
}

function riskWeight(riskState: string): number {
  switch (riskState) {
    case "liquidating":
      return 5;
    case "margin_call":
      return 4;
    case "terminated":
      return 3;
    case "warning":
      return 2;
    default:
      return 1;
  }
}

function deriveKeyTicks(
  reportEvents: ReadonlyArray<ServerEventEnvelope>,
  chains: ReadonlyArray<AuditCausalChainPayload>,
): string[] {
  const ticks = new Set<string>();
  for (const chain of chains) {
    for (const step of chain.steps) {
      if (step.tick_id) ticks.add(step.tick_id);
    }
  }
  for (const evt of reportEvents) {
    if (
      evt.type === "market.tape_alert" ||
      evt.type === "market.end_of_day" ||
      evt.type === "agent.account_snapshot" ||
      evt.type === "audit.causal_chain" ||
      evt.type === "system.error"
    ) {
      ticks.add(evt.tick_id);
    }
  }
  return Array.from(ticks).sort().slice(-12);
}

export function DossierPage() {
  const session = useSession();
  const snapshot = useSnapshot();
  const events = useEvents();

  const liveSnapshotData: SnapshotData | null =
    snapshot.phase.kind === "ready" ? snapshot.phase.snapshot : null;
  const liveSession =
    session.phase.kind === "active" || session.phase.kind === "terminal"
      ? session.phase.session
      : null;
  const liveSessionId = liveSession?.session_id ?? liveSnapshotData?.session_id ?? null;
  const [report, setReport] = useState<ReportSnapshot | null>(null);
  const [selectedChainId, setSelectedChainId] = useState<string | null>(null);
  const [selectedTickId, setSelectedTickId] = useState<string | null>(null);

  useEffect(() => {
    if (!liveSessionId) {
      setReport(null);
      return;
    }
    if (!liveSnapshotData) return;
    setReport((current) => {
      const isSameSession =
        current?.session?.session_id === liveSessionId ||
        current?.snapshot?.session_id === liveSessionId;
      if (isSameSession && current.snapshot) {
        return current;
      }
      return {
        session: liveSession,
        snapshot: liveSnapshotData,
        events: events.events.filter((evt) => DISPLAY_EVENT_TYPES.has(evt.type)),
        generatedAt: new Date().toISOString(),
      };
    });
  }, [events.events, liveSession, liveSessionId, liveSnapshotData]);

  useEffect(() => {
    setSelectedChainId(null);
    setSelectedTickId(null);
  }, [report?.session?.session_id, report?.snapshot?.session_id]);

  const snapshotData = report?.snapshot ?? null;
  const reportEvents = report?.events ?? [];
  const chains = useMemo(
    () => deriveCausalChains(snapshotData, reportEvents),
    [snapshotData, reportEvents],
  );
  const endOfDay = useMemo(() => pickLatestEndOfDay(reportEvents), [reportEvents]);

  const sessionData = report?.session ?? null;
  const sessionId = sessionData?.session_id ?? snapshotData?.session_id ?? null;
  const symbol = snapshotData?.market?.symbol ?? endOfDay?.symbol ?? "N/A";
  const startTickId = sessionData?.start_tick_id ?? "N/A";
  const endTickId = sessionData?.end_tick_id ?? snapshotData?.current_tick_id ?? "N/A";
  const collapseProbability = readCollapseProbability(snapshotData, sessionData);
  const generatedAt = report?.generatedAt ?? new Date().toISOString();

  const rankedAgents = useMemo(() => {
    return buildReportAgents(snapshotData, reportEvents)
      .sort((a, b) => riskWeight(b.risk_state) - riskWeight(a.risk_state) || a.equity - b.equity)
      .slice(0, 8);
  }, [snapshotData, reportEvents]);

  const keyTicks = useMemo(() => deriveKeyTicks(reportEvents, chains), [reportEvents, chains]);
  const selectedTickEvents = useMemo(
    () =>
      selectedTickId
        ? reportEvents.filter((evt) => evt.tick_id === selectedTickId).slice(0, 8)
        : reportEvents.slice(-8),
    [reportEvents, selectedTickId],
  );
  const selectedChain =
    chains.find((chain) => chain.chain_id === selectedChainId) ?? chains[0] ?? null;
  const severeAgents = rankedAgents.filter((agent) => riskWeight(agent.risk_state) >= 3);

  if (session.phase.kind === "none") {
    return (
      <section className="dossier-page">
        <header className="dossier-header">
          <h1>崩塌概率：N/A</h1>
        </header>
        <EmptyState label="NO SESSION" />
      </section>
    );
  }

  if (snapshot.phase.kind === "loading") {
    return (
      <section className="dossier-page">
        <header className="dossier-header">
          <h1>崩塌概率：N/A</h1>
        </header>
        <LoadingSkeleton label="LOADING DOSSIER" />
      </section>
    );
  }

  return (
    <section className="dossier-page">
      <header className="dossier-header">
        <h1>崩塌概率：{collapseProbability}</h1>
        <div className="dossier-meta">
          <span>session_id {sessionId ? displaySession(sessionId) : "N/A"}</span>
          <span>symbol {displaySymbol(symbol)}</span>
          <span>start_tick_id {formatTick(startTickId)}</span>
          <span>end_tick_id {formatTick(endTickId)}</span>
          <span>generated_at {formatTick(generatedAt)}</span>
        </div>
      </header>
      <div className="dossier-columns">
        <section>
          <h2>概述与定性</h2>
          <p className="dossier-summary-label">前端展示摘要</p>
          {chains.length === 0 ? (
            <p>暂无可展示的因果链摘要。所有结论字段以 Web API 提供为准；缺字段时统一显示 N/A。</p>
          ) : (
            chains.slice(0, 4).map((chain) => (
              <article className="dossier-chain-summary" key={chain.chain_id}>
                <button
                  className={chain.chain_id === selectedChainId ? "active" : ""}
                  type="button"
                  onClick={() => setSelectedChainId(chain.chain_id)}
                >
                  {chain.title}
                </button>
                <p>{chain.summary}</p>
              </article>
            ))
          )}
          {endOfDay && (
            <p>
              收盘价 {endOfDay.close_price.toFixed(2)}，成交额{" "}
              {endOfDay.turnover.toLocaleString("en-US")}。
            </p>
          )}
          {severeAgents.length > 0 && (
            <p>
              关键风险状态集中在{" "}
              {severeAgents
                .map((agent) => labelFrom(agentNameLabels, agent.agent_id) || agent.agent_id)
                .join("、")}
              ，风险标签来自快照或账户审计视图。
            </p>
          )}
        </section>
        <section>
          <h2>图表证据</h2>
          {chains.length === 0 ? (
            <EmptyState label="NO CAUSAL CHAIN" />
          ) : (
            <DossierPath
              chains={chains}
              selectedChainId={selectedChain?.chain_id ?? null}
              selectedTickId={selectedTickId}
            />
          )}
          {selectedChain && selectedChain.steps.length > 0 && (
            <table className="dossier-evidence-table">
              <thead>
                <tr>
                  <th>Tick</th>
                  <th>证据</th>
                  <th>事件引用</th>
                </tr>
              </thead>
              <tbody>
                {selectedChain.steps.map((step) => (
                  <tr
                    className={selectedTickId === step.tick_id ? "active" : ""}
                    key={step.step_id}
                    onClick={() => setSelectedTickId(step.tick_id)}
                  >
                    <td>{formatTick(step.tick_id)}</td>
                    <td>{step.public_text || step.label}</td>
                    <td>{step.event_ref}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
        <section>
          <h2>表格与附录</h2>
          {rankedAgents.length > 0 ? (
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
                    <td>{labelFrom(agentNameLabels, agent.agent_id) || agent.agent_id}</td>
                    <td>{labelFrom(agentTypeLabels, agent.agent_type)}</td>
                    <td>{Math.round(agent.equity).toLocaleString("en-US")}</td>
                    <td>{labelFrom(riskStateLabels, agent.risk_state)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState label="NO RISK RANK" />
          )}
          {endOfDay && (
            <div className="dragon-tiger-block">
              <h3>买方龙虎榜</h3>
              <table>
                <thead>
                  <tr>
                    <th>席位</th>
                    <th>净额</th>
                  </tr>
                </thead>
                <tbody>
                  {endOfDay.dragon_tiger.buy_rank.map((row) => (
                    <tr key={row.seat_name}>
                      <td>{row.seat_name}</td>
                      <td>{Math.round(row.net_amount).toLocaleString("en-US")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <h3>卖方龙虎榜</h3>
              <table>
                <thead>
                  <tr>
                    <th>席位</th>
                    <th>净额</th>
                  </tr>
                </thead>
                <tbody>
                  {endOfDay.dragon_tiger.sell_rank.map((row) => (
                    <tr key={row.seat_name}>
                      <td>{row.seat_name}</td>
                      <td>{Math.round(row.net_amount).toLocaleString("en-US")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="dossier-appendix">
            <h3>关键 Tick</h3>
            <table>
              <tbody>
                {keyTicks.map((tickId) => (
                  <tr
                    className={selectedTickId === tickId ? "active" : ""}
                    key={tickId}
                    onClick={() => setSelectedTickId(tickId)}
                  >
                    <td>{formatTick(tickId)}</td>
                    <td>{reportEvents.filter((evt) => evt.tick_id === tickId).length} 条可展示事件</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <h3>事件引用附录</h3>
            <table>
              <tbody>
                {selectedTickEvents.map((evt) => (
                  <tr className={selectedTickId === evt.tick_id ? "active" : ""} key={evt.seq}>
                    <td>{eventReference(evt)}</td>
                    <td>{formatTick(evt.server_time)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </section>
  );
}
