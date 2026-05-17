import { useEffect, useMemo } from "react";
import { EmptyState } from "../components/common/EmptyState";
import { LoadingSkeleton } from "../components/common/LoadingSkeleton";
import {
  accountFieldLabels,
  agentNameLabels,
  labelFrom,
  riskStateLabels,
} from "../i18n/labels";
import { useEvents, useSession, useSnapshot, useUI } from "../state";
import {
  deriveAccountSnapshots,
  deriveAuditGraph,
  deriveCausalChains,
} from "../utils/derive";
import { formatAccountValue, formatTick } from "../utils/format";
import type { AgentSummary, RiskState, SnapshotData } from "../types/api";

const RISK_PRIORITY: Record<RiskState, number> = {
  terminated: 5,
  liquidating: 4,
  margin_call: 3,
  warning: 2,
  normal: 1,
};

function pickDefaultAgentId(agents: ReadonlyArray<AgentSummary>): string | null {
  if (agents.length === 0) return null;
  const ranked = [...agents].sort(
    (a, b) => (RISK_PRIORITY[b.risk_state] ?? 0) - (RISK_PRIORITY[a.risk_state] ?? 0),
  );
  return ranked[0].agent_id;
}

export function EntityPage() {
  const session = useSession();
  const snapshot = useSnapshot();
  const events = useEvents();
  const ui = useUI();

  const snapshotData: SnapshotData | null =
    snapshot.phase.kind === "ready" ? snapshot.phase.snapshot : null;
  const agents = snapshotData?.agents ?? [];

  const accountMap = useMemo(() => deriveAccountSnapshots(events.events), [events.events]);
  const auditGraph = useMemo(
    () => deriveAuditGraph(snapshotData, events.events),
    [snapshotData, events.events],
  );
  const chains = useMemo(
    () => deriveCausalChains(snapshotData, events.events),
    [snapshotData, events.events],
  );

  useEffect(() => {
    if (ui.selectedAgentId) return;
    const defaultId = pickDefaultAgentId(agents);
    if (defaultId) ui.setSelectedAgentId(defaultId);
  }, [ui, agents]);

  if (session.phase.kind === "none") {
    return (
      <section className="entity-page">
        <header className="terminal-header">
          <span>智能体解剖室</span>
          <span>NO SESSION</span>
        </header>
        <div className="live-empty">
          <EmptyState label="NO SESSION // 请先创建会话" />
        </div>
      </section>
    );
  }

  if (snapshot.phase.kind === "loading") {
    return (
      <section className="entity-page">
        <header className="terminal-header">
          <span>智能体解剖室</span>
        </header>
        <LoadingSkeleton label="LOADING ROSTER" />
      </section>
    );
  }

  if (snapshot.phase.kind === "error") {
    return (
      <section className="entity-page">
        <header className="terminal-header">
          <span>智能体解剖室</span>
        </header>
        <div className="live-empty">
          <EmptyState label={`SNAPSHOT ERROR // ${snapshot.phase.error.code}`} />
        </div>
      </section>
    );
  }

  if (agents.length === 0) {
    return (
      <section className="entity-page">
        <header className="terminal-header">
          <span>智能体解剖室</span>
        </header>
        <div className="live-empty">
          <EmptyState label="NO AGENT ROSTER" />
        </div>
      </section>
    );
  }

  const selectedId = ui.selectedAgentId ?? agents[0]?.agent_id;
  const selectedAgent = agents.find((a) => a.agent_id === selectedId) ?? agents[0];
  const account = selectedAgent ? accountMap.get(selectedAgent.agent_id) : undefined;

  return (
    <section className="entity-page">
      <header className="terminal-header">
        <span>智能体解剖室</span>
        <span>[{labelFrom(agentNameLabels, selectedAgent.agent_id) || selectedAgent.agent_id}]</span>
      </header>
      <div className="entity-layout">
        <aside className="roster">
          {agents.map((agent) => (
            <button
              className={agent.agent_id === selectedAgent.agent_id ? "active" : ""}
              type="button"
              key={agent.agent_id}
              onClick={() => ui.setSelectedAgentId(agent.agent_id)}
            >
              <span>[{labelFrom(agentNameLabels, agent.agent_id) || agent.agent_id}]</span>
              {agent.risk_state !== "normal" && (
                <mark>{labelFrom(riskStateLabels, agent.risk_state)}</mark>
              )}
            </button>
          ))}
        </aside>
        <section className="quadrants">
          <div className="panel account-table">
            <h2>资产表</h2>
            {[
              ["cash", account?.cash],
              ["available_cash", account?.available_cash],
              ["positions", account ? Object.values(account.positions).join(" / ") : "—"],
              [
                "available_shares",
                account ? Object.values(account.available_shares).join(" / ") : "—",
              ],
              [
                "frozen_shares",
                account ? Object.values(account.frozen_shares).join(" / ") : "—",
              ],
              ["market_value", account?.market_value],
              ["equity", account?.equity ?? selectedAgent.equity],
              ["risk_state", account?.risk_state ?? selectedAgent.risk_state],
            ].map(([label, value]) => (
              <div className="table-line" key={String(label)}>
                <span>{labelFrom(accountFieldLabels, String(label))}</span>
                <strong>{formatAccountValue(String(label), value)}</strong>
              </div>
            ))}
            {!account && (
              <div className="account-stub">NO PRIVATE SNAPSHOT // 等待 agent.account_snapshot</div>
            )}
          </div>
          <div className="panel belief-track">
            <h2>信念轨迹</h2>
            <BeliefTrack
              agentId={selectedAgent.agent_id}
              graphBelief={auditGraph.nodes.find((n) => n.agent_id === selectedAgent.agent_id)?.belief_score}
            />
          </div>
          <div className="panel audit-room">
            <h2>脱敏审计室</h2>
            {chains.length === 0 ? (
              <EmptyState label="NO PUBLIC CAUSAL CHAIN" />
            ) : (
              chains.map((chain) => (
                <article key={chain.chain_id}>
                  <h3>{chain.title}</h3>
                  <p>{chain.summary}</p>
                  {chain.steps.slice(0, 6).map((step) => (
                    <div className="audit-step" key={step.step_id}>
                      <time>{formatTick(step.tick_id)}</time>
                      <strong>{step.label}</strong>
                      <span>{step.public_text}</span>
                    </div>
                  ))}
                </article>
              ))
            )}
          </div>
        </section>
      </div>
    </section>
  );
}

function BeliefTrack({ agentId, graphBelief }: { agentId: string; graphBelief: number | undefined }) {
  if (graphBelief === undefined) {
    return <EmptyState label="NO BELIEF HISTORY" />;
  }
  // Until history accumulation lands, render the latest single point.
  const y = 88 - graphBelief * 76;
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label={`${agentId} belief`}>
      <polyline points={`2,${y} 98,${y}`} fill="none" stroke="#002fa7" strokeWidth="1.4" />
      <circle cx="50" cy={y} r="2" fill="#002fa7" />
      <text x="53" y={y - 2} fontSize="4">
        C:{graphBelief.toFixed(2)}
      </text>
    </svg>
  );
}
