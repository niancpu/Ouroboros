import { memo } from "react";
import { Crosshair, Eye, Network, RotateCcw } from "lucide-react";
import type {
  AgentSummary,
  AuditGraphNode,
  AuditGraphPayload,
  LifecycleState,
} from "../../types/api";
import { agentTypeLabels, labelFrom, riskStateLabels } from "../../i18n/labels";
import { formatAgentCode, formatPercent, formatTick } from "../../utils/format";
import {
  bezierPath,
  buildSpotlightIds,
  deterministicNodePoint,
  positionExposure,
  pruneGraphEdges,
  type EdgeFilterMode,
  type NodePoint,
} from "../../utils/graph";
import { NodeGlyph } from "./NodeGlyph";

interface TopologyProps {
  agents: AgentSummary[];
  graph: AuditGraphPayload;
  agentLifecycleMap: Map<string, LifecycleState>;
  edgeMode: EdgeFilterMode;
  hoveredAgentId: string | null;
  selectedAgentId: string | null;
  selectedReasonRef: string | null;
  tickId: string;
  onHoverAgent: (id: string | null) => void;
  onSelectAgent: (id: string) => void;
  onSelectReason: (ref: string | null) => void;
  onEdgeModeChange: (mode: EdgeFilterMode) => void;
}

function fallbackNodesFromAgents(agents: ReadonlyArray<AgentSummary>): AuditGraphNode[] {
  const maxEquity = agents.reduce((max, agent) => Math.max(max, agent.equity), 1);
  return agents.map((agent) => ({
    agent_id: agent.agent_id,
    agent_type: agent.agent_type,
    belief_score: Math.max(0, Math.min(1, agent.equity / Math.max(maxEquity, 1))),
    position_value: agent.position_value,
    risk_state: agent.risk_state,
  }));
}

function chooseShape(agentType: string): "circle" | "square" {
  return agentType === "retail" || agentType === "retail_cluster" ? "square" : "circle";
}

export function Topology({
  agents,
  graph,
  agentLifecycleMap,
  edgeMode,
  hoveredAgentId,
  selectedAgentId,
  selectedReasonRef,
  tickId,
  onHoverAgent,
  onSelectAgent,
  onSelectReason,
  onEdgeModeChange,
}: TopologyProps) {
  const graphNodes: AuditGraphNode[] = graph.nodes.length
    ? graph.nodes
    : fallbackNodesFromAgents(agents);
  const nodes: Array<AuditGraphNode & NodePoint> = graphNodes.map((node, index) => {
    const point = deterministicNodePoint(index, graphNodes.length);
    return {
      ...node,
      belief_score: clampFinite(node.belief_score, 0),
      position_value: clampFinite(node.position_value, 0),
      risk_state: node.risk_state,
      ...point,
    };
  });
  const nodeById = new Map(nodes.map((node) => [node.agent_id, node]));
  const visibleEdges = pruneGraphEdges(graph.edges, selectedAgentId, edgeMode);
  const spotlightIds = buildSpotlightIds(hoveredAgentId, graph.edges);

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
            <path d="M 10 0 L 0 0 0 10" fill="none" stroke="var(--color-text-primary, #1a1a2e)" strokeOpacity="0.04" strokeWidth="0.5" />
          </pattern>
          <pattern
            id="node-suspended-stripes"
            width="2"
            height="2"
            patternUnits="userSpaceOnUse"
            patternTransform="rotate(45)"
          >
            <line x1="0" y1="0" x2="0" y2="2" stroke="var(--color-text-primary, #1a1a2e)" strokeWidth="0.4" />
          </pattern>
          <marker id="sharp-arrow" viewBox="0 0 6 6" refX="5.5" refY="3" markerWidth="4" markerHeight="4" orient="auto">
            <path d="M 0 0 L 6 3 L 0 6 Z" fill="var(--color-text-primary, #1a1a2e)" />
          </marker>
          <clipPath id="belief-top-circle">
            <rect x="-12" y="-12" width="24" height="12" />
          </clipPath>
        </defs>
        <rect x="0" y="0" width="100" height="100" fill="url(#engineering-grid)" />
        <text x="2" y="5" fontSize="2.3" fill="var(--color-text-secondary, #6b7280)">
          X:-240.50 Y:112.00 // SCALE 1:1
        </text>
        <text x="66" y="96" fontSize="2.3" fill="var(--color-text-secondary, #6b7280)">
          TICK {formatTick(tickId)}
        </text>
        {visibleEdges.map((edge, index) => {
          const source = nodeById.get(edge.source);
          const target = nodeById.get(edge.target);
          if (!source || !target) return null;
          const isDimmed = spotlightIds
            ? !spotlightIds.has(edge.source) && !spotlightIds.has(edge.target)
            : false;
          const isSelected = edge.reason_ref === selectedReasonRef;
          return (
            <path
              className={isDimmed ? "graph-dimmed" : ""}
              key={`${edge.source}-${edge.target}-${edge.reason_ref}`}
              d={bezierPath(source, target)}
              fill="none"
              markerEnd="url(#sharp-arrow)"
              onClick={() => onSelectReason(edge.reason_ref)}
              stroke={isSelected || index % 2 === 0 ? "var(--color-accent, #1e3a5f)" : "var(--color-text-primary, #1a1a2e)"}
              strokeDasharray={
                edge.weight < 0.3 ? "1 2" : index % 3 === 0 ? "4 3" : undefined
              }
              strokeWidth="0.5"
            >
              <title>
                {edge.public_reason} W:{edge.weight.toFixed(2)}
              </title>
            </path>
          );
        })}
        {nodes.map((node) => {
          const lifecycleState = agentLifecycleMap.get(node.agent_id);
          const shape = chooseShape(node.agent_type);
          const code = formatAgentCode(node.agent_id, graphNodes);
          return (
            <g
              className={spotlightIds && !spotlightIds.has(node.agent_id) ? "graph-dimmed" : ""}
              key={node.agent_id}
              onClick={() => onSelectAgent(node.agent_id)}
              onMouseEnter={() => onHoverAgent(node.agent_id)}
              onMouseLeave={() => onHoverAgent(null)}
            >
              {node.agent_id === selectedAgentId && (
                <rect
                  x={node.x - 6}
                  y={node.y - 6}
                  width="12"
                  height="12"
                  fill="none"
                  stroke="var(--color-text-secondary, #6b7280)"
                  strokeDasharray="1.4 1.4"
                  strokeWidth="0.5"
                />
              )}
              <NodeGlyph
                node={node}
                allNodes={graphNodes}
                shape={shape}
                lifecycleState={lifecycleState}
              />
              <line
                x1={node.x + 4.8}
                y1={node.y}
                x2={node.x + 11}
                y2={node.y}
                stroke="var(--color-border-strong, #d1d5db)"
                strokeWidth="0.35"
              />
              <text x={node.x + 11.5} y={node.y + 0.8} fontSize="2.2" fill="var(--color-text-secondary, #6b7280)">
                [{code}] C:{node.belief_score.toFixed(2)} P:
                {formatPercent(positionExposure(node, graphNodes))}
              </text>
              <title>
                {node.agent_id} / {labelFrom(agentTypeLabels, node.agent_type)} /{" "}
                {labelFrom(riskStateLabels, node.risk_state)} / belief{" "}
                {node.belief_score.toFixed(2)} / position{" "}
                {formatPercent(positionExposure(node, graphNodes))}
              </title>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function clampFinite(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}
