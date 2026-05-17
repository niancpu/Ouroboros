import type { AuditGraphNode, LifecycleState } from "../../types/api";
import { positionExposure, type NodePoint } from "../../utils/graph";

const C = {
  accent: "var(--color-accent, #1e3a5f)",
  danger: "var(--color-danger, #b91c1c)",
  text: "var(--color-text-primary, #1a1a2e)",
  surface: "var(--color-surface, #ffffff)",
} as const;

interface NodeGlyphProps {
  node: AuditGraphNode & NodePoint;
  allNodes: ReadonlyArray<AuditGraphNode>;
  shape: "circle" | "square";
  lifecycleState?: LifecycleState;
}

interface LifecycleVisual {
  stroke: string;
  fillOverride?: string;
  rightMarks: number;
  markColor: string;
}

function resolveLifecycleVisual(
  riskState: AuditGraphNode["risk_state"],
  lifecycleState?: LifecycleState,
): LifecycleVisual {
  const warningStroke = riskState === "warning" ? C.accent : C.text;
  switch (lifecycleState) {
    case "margin_call":
      return { stroke: C.danger, rightMarks: 1, markColor: C.danger };
    case "liquidating":
      return { stroke: C.danger, rightMarks: 2, markColor: C.danger };
    case "terminated":
      return { stroke: C.text, rightMarks: 2, markColor: C.text };
    case "suspended":
      return {
        stroke: C.text,
        fillOverride: "url(#node-suspended-stripes)",
        rightMarks: 0,
        markColor: C.text,
      };
    case "active":
    default:
      return { stroke: warningStroke, rightMarks: 0, markColor: C.text };
  }
}

function renderRightMarks(
  x: number,
  y: number,
  count: number,
  color: string,
  half: number,
) {
  if (count <= 0) return null;
  const marks = [];
  const length = count === 2 ? 5 : 4;
  const baseX = x + half + 0.4;
  for (let i = 0; i < count; i += 1) {
    const offsetY = count === 1 ? half - 0.2 : i === 0 ? half - 1.0 : half - 0.2;
    marks.push(
      <line
        key={`life-mark-${i}`}
        x1={baseX}
        y1={y + offsetY}
        x2={baseX + length * 0.4}
        y2={y + offsetY}
        stroke={color}
        strokeWidth="1"
      />,
    );
  }
  return <>{marks}</>;
}

export function NodeGlyph({ node, allNodes, shape, lifecycleState }: NodeGlyphProps) {
  const beliefScore = clampNumber(node.belief_score, 0, 1);
  const fillHeight = Math.max(0, Math.min(1, Math.abs(beliefScore - 0.5) * 2)) * 5;
  const beliefFill =
    beliefScore > 0.6
      ? C.accent
      : beliefScore < 0.4
      ? C.text
      : C.surface;
  const exposure = clampNumber(positionExposure(node, allNodes), 0, 1);
  const visual = resolveLifecycleVisual(node.risk_state, lifecycleState);

  if (shape === "square") {
    const half = 4.2;
    return (
      <>
        <rect
          x={node.x - half}
          y={node.y - half}
          width={half * 2}
          height={half * 2}
          fill={visual.fillOverride ?? C.surface}
          stroke={visual.stroke}
          strokeWidth="0.6"
        />
        {!visual.fillOverride && (
          <rect
            x={node.x - half}
            y={node.y - half}
            width={half * 2}
            height={fillHeight}
            fill={beliefFill}
          />
        )}
        <line
          x1={node.x - 3.4}
          y1={node.y + 3.5}
          x2={node.x - 3.4 + exposure * 6.8}
          y2={node.y + 3.5}
          stroke={C.text}
          strokeWidth="0.7"
        />
        {renderRightMarks(node.x, node.y - half, visual.rightMarks, visual.markColor, half)}
      </>
    );
  }

  const radius = 4.4;
  return (
    <>
      <circle
        cx={node.x}
        cy={node.y}
        r={radius}
        fill={visual.fillOverride ?? C.surface}
        stroke={visual.stroke}
        strokeWidth="0.6"
      />
      {!visual.fillOverride && (
        <g transform={`translate(${node.x} ${node.y})`} clipPath="url(#belief-top-circle)">
          <circle cx="0" cy="0" r={radius} fill={beliefFill} />
        </g>
      )}
      <line
        x1={node.x - 3.3}
        y1={node.y + 3.5}
        x2={node.x - 3.3 + exposure * 6.6}
        y2={node.y + 3.5}
        stroke={C.text}
        strokeWidth="0.7"
      />
      {renderRightMarks(node.x, node.y - radius, visual.rightMarks, visual.markColor, radius)}
    </>
  );
}

function clampNumber(value: unknown, min: number, max: number): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return min;
  }
  return Math.max(min, Math.min(max, value));
}
