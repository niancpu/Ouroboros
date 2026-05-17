import type {
  AgentAccountSnapshotPayload,
  AgentSummary,
  AuditGraphEdge,
  AuditGraphNode,
} from "../../types/api";
import { agentTypeLabels, labelFrom, riskStateLabels } from "../../i18n/labels";
import { displayAgentName, formatPercent } from "../../utils/format";
import { aggregatePositionShare, portfolioPositionRatio } from "../../utils/graph";
import { EmptyState } from "../common/EmptyState";

interface AgentInspectorPanelProps {
  selectedAgent: AgentAccountSnapshotPayload | AgentSummary | null;
  selectedNode: AuditGraphNode | null;
  selectedEdges: AuditGraphEdge[];
  allNodes: AuditGraphNode[];
  onSelectReason: (ref: string | null) => void;
}

export function AgentInspectorPanel({
  selectedAgent,
  selectedNode,
  selectedEdges,
  allNodes,
  onSelectReason,
}: AgentInspectorPanelProps) {
  return (
    <section className="agent-inspector">
      <h2>节点详情</h2>
      {selectedAgent && selectedNode ? (
        <div className="inspector-grid">
          <span>名称</span>
          <strong>{displayAgentName(selectedAgent.agent_id)}</strong>
          <span>ID</span>
          <strong>{selectedAgent.agent_id}</strong>
          <span>类型</span>
          <strong>{labelFrom(agentTypeLabels, selectedAgent.agent_type)}</strong>
          <span>风险</span>
          <strong>{labelFrom(riskStateLabels, selectedAgent.risk_state)}</strong>
          <span>信念</span>
          <strong>{selectedNode.belief_score.toFixed(2)}</strong>
          <span>组合仓位</span>
          <strong>{formatPercent(portfolioPositionRatio(selectedAgent))}</strong>
          <span>总持仓占比</span>
          <strong>{formatPercent(aggregatePositionShare(selectedNode, allNodes))}</strong>
        </div>
      ) : (
        <EmptyState label="未选择节点" />
      )}
      <div className="chain-list">
        {selectedEdges.length ? (
          selectedEdges.map((edge) => (
            <button
              type="button"
              key={edge.reason_ref}
              onClick={() => onSelectReason(edge.reason_ref)}
            >
              {edge.reason_ref} W:{edge.weight.toFixed(2)}
            </button>
          ))
        ) : (
          <span>暂无公开因果链</span>
        )}
      </div>
    </section>
  );
}
