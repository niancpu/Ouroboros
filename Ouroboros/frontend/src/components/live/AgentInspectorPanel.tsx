import type {
  AgentAccountSnapshotPayload,
  AgentSummary,
  AuditGraphEdge,
  AuditGraphNode,
} from "../../types/api";
import { agentTypeLabels, labelFrom, riskStateLabels } from "../../i18n/labels";
import { formatPercent } from "../../utils/format";
import { positionExposure } from "../../utils/graph";
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
          <strong>{formatPercent(positionExposure(selectedNode, allNodes))}</strong>
        </div>
      ) : (
        <EmptyState label="NO AGENT SELECTED" />
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
          <span>NO PUBLIC CAUSAL CHAIN</span>
        )}
      </div>
    </section>
  );
}
