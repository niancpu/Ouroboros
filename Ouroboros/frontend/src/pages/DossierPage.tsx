import { useMemo } from "react";
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
import { deriveCausalChains } from "../utils/derive";
import { displaySession, displaySymbol, formatTick } from "../utils/format";
import type { MarketEndOfDayPayload, ServerEventEnvelope, SnapshotData } from "../types/api";

function pickLatestEndOfDay(events: ReadonlyArray<ServerEventEnvelope>): MarketEndOfDayPayload | null {
  for (let i = events.length - 1; i >= 0; i -= 1) {
    if (events[i].type === "market.end_of_day") {
      return events[i].payload as MarketEndOfDayPayload;
    }
  }
  return null;
}

export function DossierPage() {
  const session = useSession();
  const snapshot = useSnapshot();
  const events = useEvents();

  const snapshotData: SnapshotData | null =
    snapshot.phase.kind === "ready" ? snapshot.phase.snapshot : null;
  const chains = useMemo(
    () => deriveCausalChains(snapshotData, events.events),
    [snapshotData, events.events],
  );
  const endOfDay = useMemo(() => pickLatestEndOfDay(events.events), [events.events]);

  const sessionId = session.phase.kind === "active" || session.phase.kind === "terminal"
    ? session.phase.session.session_id
    : null;
  const symbol = snapshotData?.market?.symbol ?? "demo_stock";
  const currentTickId = session.phase.kind === "active" || session.phase.kind === "terminal"
    ? session.phase.session.current_tick_id
    : "";

  const rankedAgents = useMemo(() => {
    if (!snapshotData) return [];
    return [...snapshotData.agents].sort((a, b) => a.equity - b.equity).slice(0, 8);
  }, [snapshotData]);

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
        <h1>崩塌概率：N/A</h1>
        <div>
          <span>会话 {sessionId ? displaySession(sessionId) : "—"}</span>
          <span>标的 {displaySymbol(symbol)}</span>
          <span>节拍 {formatTick(currentTickId)}</span>
          <span>生成 {formatTick(new Date().toISOString())}</span>
        </div>
      </header>
      <div className="dossier-columns">
        <section>
          <h2>概述与定性</h2>
          {chains.length === 0 ? (
            <p>暂无可展示的因果链摘要。所有结论字段以 Web API 提供为准；缺字段时统一显示 N/A。</p>
          ) : (
            chains.slice(0, 2).map((chain) => (
              <p key={chain.chain_id}>{chain.summary}</p>
            ))
          )}
          {endOfDay && (
            <p>
              收盘价 {endOfDay.close_price.toFixed(2)}，成交额{" "}
              {endOfDay.turnover.toLocaleString("en-US")}。
            </p>
          )}
        </section>
        <section>
          <h2>图表证据</h2>
          {chains.length === 0 ? (
            <EmptyState label="NO CAUSAL CHAIN" />
          ) : (
            <DossierPath chains={chains} />
          )}
        </section>
        <section>
          <h2>风险排行 / 龙虎榜</h2>
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
            </div>
          )}
        </section>
      </div>
    </section>
  );
}
