import type { AgentSummary, AuditGraphEdge, AuditGraphNode } from "../types/api";

export interface NodePoint {
  x: number;
  y: number;
}

export type EdgeFilterMode = "current" | "selected" | "strong";

const DEFAULT_RADIUS_X = 36;
const DEFAULT_RADIUS_Y = 28;
const STRONG_WEIGHT = 0.3;
const EDGE_HARD_LIMIT = 48;

export function deterministicNodePoint(index: number, total: number): NodePoint {
  const ring = index % 3;
  const radiusScale = ring === 0 ? 0.55 : ring === 1 ? 0.78 : 1;
  const angle = -Math.PI / 2 + (index * Math.PI * 2 * 0.61803398875) % (Math.PI * 2);
  return {
    x: 50 + Math.cos(angle) * DEFAULT_RADIUS_X * radiusScale,
    y: 50 + Math.sin(angle) * DEFAULT_RADIUS_Y * radiusScale,
  };
}

export function positionExposure(
  node: Pick<AuditGraphNode, "position_value">,
  allNodes: ReadonlyArray<Pick<AuditGraphNode, "position_value">>,
): number {
  const maxPosition = allNodes.reduce(
    (max, entry) => Math.max(max, entry.position_value ?? 0),
    1,
  );
  if (!maxPosition) return 0;
  return Math.max(0, Math.min(1, (node.position_value ?? 0) / maxPosition));
}

export function pruneGraphEdges(
  edges: ReadonlyArray<AuditGraphEdge>,
  selectedAgentId: string | null,
  edgeMode: EdgeFilterMode,
): AuditGraphEdge[] {
  if (edges.length === 0) return [];
  const strongEdges = edges.filter((edge) => edge.weight >= STRONG_WEIGHT);
  const selectedEdges = selectedAgentId
    ? edges.filter(
        (edge) => edge.source === selectedAgentId || edge.target === selectedAgentId,
      )
    : [];
  let source: ReadonlyArray<AuditGraphEdge>;
  if (edgeMode === "selected") source = selectedEdges;
  else if (edgeMode === "strong") source = strongEdges;
  else source = strongEdges.length > 0 ? strongEdges : edges;
  return [...source].sort((a, b) => b.weight - a.weight).slice(0, EDGE_HARD_LIMIT);
}

export function agentSummaryToGraphNode(
  agent: AgentSummary,
  beliefScore: number,
): AuditGraphNode {
  return {
    agent_id: agent.agent_id,
    agent_type: agent.agent_type,
    belief_score: beliefScore,
    position_value: agent.position_value,
    risk_state: agent.risk_state,
  };
}

export function bezierPath(source: NodePoint, target: NodePoint): string {
  const dx = target.x - source.x;
  return `M ${source.x} ${source.y} C ${source.x + dx * 0.45} ${source.y}, ${target.x - dx * 0.45} ${target.y}, ${target.x} ${target.y}`;
}

export function buildSpotlightIds(
  hoveredAgentId: string | null,
  edges: ReadonlyArray<AuditGraphEdge>,
): Set<string> | null {
  if (!hoveredAgentId) return null;
  const ids = new Set<string>([hoveredAgentId]);
  for (const edge of edges) {
    if (edge.source === hoveredAgentId) ids.add(edge.target);
    if (edge.target === hoveredAgentId) ids.add(edge.source);
  }
  return ids;
}
