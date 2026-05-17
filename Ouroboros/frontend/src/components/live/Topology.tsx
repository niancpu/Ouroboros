import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GraphChart } from "echarts/charts";
import { TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { Minus, Maximize2, Plus } from "lucide-react";
import type {
  AgentSummary,
  AuditGraphEdge,
  AuditGraphNode,
  AuditGraphPayload,
  LifecycleState,
} from "../../types/api";
import { agentTypeLabels, labelFrom, riskStateLabels } from "../../i18n/labels";
import { formatAgentCode, formatPercent, formatTick } from "../../utils/format";
import {
  buildSpotlightIds,
  deterministicNodePoint,
  positionExposure,
  pruneGraphEdges,
  type EdgeFilterMode,
  type NodePoint,
} from "../../utils/graph";

echarts.use([GraphChart, TooltipComponent, CanvasRenderer]);

type ChartInstance = ReturnType<typeof echarts.init>;

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

const GRAPH_SERIES_ID = "audit-graph";
const GRAPH_ZOOM_STEP = 0.16;

const C = {
  accent: "#0037c8",
  danger: "#b91c1c",
  text: "#000000",
  secondary: "#2f2f2f",
  surface: "#ffffff",
} as const;

type TopologyNode = AuditGraphNode & NodePoint;

interface ChartNodeDatum {
  id: string;
  name: string;
  agentId: string;
  x: number;
  y: number;
  value: number;
  sanitizedTooltip: string;
  symbol: "circle";
  symbolSize: number;
  itemStyle: {
    color: string;
    borderColor: string;
    borderWidth: number;
    opacity: number;
  };
}

interface ChartEdgeDatum {
  source: string;
  target: string;
  reasonRef: string;
  publicReason: string;
  weight: number;
  lineStyle: {
    color: string;
    width: number;
    opacity: number;
    type: "solid" | "dashed" | "dotted";
    curveness: number;
  };
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
  const chartHostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ChartInstance | null>(null);
  const latestNodesRef = useRef<TopologyNode[]>([]);
  const latestGraphNodesRef = useRef<AuditGraphNode[]>([]);
  const latestSelectedAgentIdRef = useRef<string | null>(null);
  const latestLifecycleMapRef = useRef<Map<string, LifecycleState>>(agentLifecycleMap);
  const latestOnHoverAgentRef = useRef(onHoverAgent);
  const latestOnSelectAgentRef = useRef(onSelectAgent);
  const latestOnSelectReasonRef = useRef(onSelectReason);
  const refreshGraphicOverlayRef = useRef<() => void>(() => {});
  const overlayTimerRef = useRef<number | null>(null);
  const [zoomLevel, setZoomLevel] = useState(1);

  const graphNodes: AuditGraphNode[] = graph.nodes.length
    ? graph.nodes
    : fallbackNodesFromAgents(agents);
  const nodes: TopologyNode[] = graphNodes.map((node, index) => {
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
  const option = useMemo(() => {
    const chartNodes: ChartNodeDatum[] = nodes.map((node) => {
      const lifecycleState = agentLifecycleMap.get(node.agent_id);
      const isSelected = node.agent_id === selectedAgentId;
      const isDimmed = spotlightIds ? !spotlightIds.has(node.agent_id) : false;
      const isBlue = isSelected || node.belief_score >= 0.6 || node.risk_state === "warning";
      const stroke =
        lifecycleState === "margin_call" || lifecycleState === "liquidating"
          ? C.danger
          : isBlue
            ? C.accent
            : C.text;
      return {
        id: node.agent_id,
        name: node.agent_id,
        agentId: node.agent_id,
        x: node.x,
        y: node.y,
        value: clampFinite(node.belief_score, 0),
        sanitizedTooltip: [
          node.agent_id,
          labelFrom(agentTypeLabels, node.agent_type),
          labelFrom(riskStateLabels, node.risk_state),
          `C:${node.belief_score.toFixed(2)}`,
          `P:${formatPercent(positionExposure(node, graphNodes))}`,
        ].join(" / "),
        symbol: "circle",
        symbolSize: 16,
        itemStyle: {
          color: C.surface,
          borderColor: stroke,
          borderWidth: isSelected ? 2 : 1.2,
          opacity: isDimmed ? 0.1 : 1,
        },
      };
    });

    const chartEdges: ChartEdgeDatum[] = visibleEdges.flatMap((edge, index) => {
      if (!nodeById.has(edge.source) || !nodeById.has(edge.target)) return [];
      const isDimmed = spotlightIds
        ? !spotlightIds.has(edge.source) && !spotlightIds.has(edge.target)
        : false;
      const isSelected = edge.reason_ref === selectedReasonRef;
      const isBlue = isSelected || index % 2 === 0;
      return [
        {
          source: edge.source,
          target: edge.target,
          reasonRef: edge.reason_ref,
          publicReason: edge.public_reason,
          weight: edge.weight,
          lineStyle: {
            color: isBlue ? C.accent : C.text,
            width: isSelected ? 1.35 : 1,
            opacity: isDimmed ? 0.1 : edge.weight < 0.3 ? 0.46 : 0.82,
            type: edge.weight < 0.3 ? "dotted" : index % 3 === 0 ? "dashed" : "solid",
            curveness: edgeCurveness(edge, index),
          },
        },
      ];
    });

    return {
      animation: false,
      backgroundColor: "transparent",
      tooltip: {
        trigger: "item",
        confine: true,
        borderColor: C.text,
        borderWidth: 1,
        backgroundColor: C.surface,
        textStyle: {
          color: C.text,
          fontFamily: "JetBrains Mono, Courier New, monospace",
          fontSize: 11,
        },
        extraCssText: "box-shadow:none;border-radius:0;",
        formatter(params: unknown) {
          const item = params as {
            dataType?: string;
            data?: Partial<ChartNodeDatum & ChartEdgeDatum>;
          };
          if (item.dataType === "edge") {
            return `${item.data?.publicReason ?? "PUBLIC REASON"}<br/>W:${formatEdgeWeight(item.data?.weight)}`;
          }
          return item.data?.sanitizedTooltip ?? "";
        },
      },
      series: [
        {
          id: GRAPH_SERIES_ID,
          type: "graph",
          layout: "none",
          roam: true,
          zoom: zoomLevel,
          center: [50, 50],
          data: chartNodes,
          links: chartEdges,
          edgeSymbol: ["none", "arrow"],
          edgeSymbolSize: [0, 7],
          cursor: "pointer",
          label: {
            show: false,
          },
          lineStyle: {
            width: 1,
            color: C.text,
            curveness: 0.16,
          },
        },
      ],
    };
  }, [
    agentLifecycleMap,
    graphNodes,
    nodeById,
    nodes,
    selectedAgentId,
    selectedReasonRef,
    spotlightIds,
    visibleEdges,
    zoomLevel,
  ]);

  const refreshGraphicOverlay = useCallback(() => {
    const chart = chartRef.current;
    if (!chart || chart.isDisposed()) return;
    const width = chart.getWidth();
    const height = chart.getHeight();
    const elements: unknown[] = [
      {
        type: "text",
        left: 12,
        top: 12,
        silent: true,
        style: watermarkText(`X:-240.50 Y:112.00 // SCALE ${zoomLevel.toFixed(2)}`),
      },
      {
        type: "text",
        right: 12,
        bottom: 10,
        silent: true,
        style: watermarkText(`TICK ${formatTick(tickId)} // ECHARTS GRAPH`),
      },
    ];

    latestNodesRef.current.forEach((node) => {
      const pixel = chart.convertToPixel({ seriesId: GRAPH_SERIES_ID }, [node.x, node.y]);
      if (!Array.isArray(pixel)) return;
      const [x, y] = pixel;
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;

      const allNodes = latestGraphNodesRef.current;
      const lifecycleState = latestLifecycleMapRef.current.get(node.agent_id);
      const isSelected = node.agent_id === latestSelectedAgentIdRef.current;
      const exposure = positionExposure(node, allNodes);
      const labelRight = x < width - 172;
      const elbowX = labelRight ? x + 20 : x - 20;
      const labelX = labelRight ? elbowX + 6 : elbowX - 6;
      const labelY = Math.max(18, Math.min(height - 18, y - 14));
      const code = formatAgentCode(node.agent_id, allNodes);
      const dimmed = spotlightIds && !spotlightIds.has(node.agent_id);
      const opacity = dimmed ? 0.1 : 1;

      if (isSelected) {
        elements.push({
          type: "rect",
          silent: true,
          shape: { x: x - 12, y: y - 12, width: 24, height: 24 },
          style: {
            fill: "transparent",
            stroke: C.text,
            lineDash: [4, 3],
            lineWidth: 1,
            opacity,
          },
        });
      }

      elements.push(
        {
          type: "line",
          silent: true,
          shape: { x1: x - 5.5, y1: y + 6.4, x2: x - 5.5 + exposure * 11, y2: y + 6.4 },
          style: { stroke: C.text, lineWidth: 1, opacity },
        },
        {
          type: "polyline",
          silent: true,
          shape: {
            points: [
              [x + (labelRight ? 9 : -9), y],
              [elbowX, y],
              [elbowX, labelY],
            ],
          },
          style: { stroke: C.text, fill: "transparent", lineWidth: 1, opacity },
        },
        {
          type: "text",
          silent: true,
          x: labelX,
          y: labelY - 7,
          style: {
            text: `[${code}] C:${node.belief_score.toFixed(2)} P:${formatPercent(exposure)}`,
            fill: dimmed ? "rgba(0,0,0,0.1)" : C.secondary,
            font: "10px JetBrains Mono, Courier New, monospace",
            align: labelRight ? "left" : "right",
            verticalAlign: "middle",
          },
        },
      );

      if (lifecycleState === "margin_call" || lifecycleState === "liquidating") {
        elements.push({
          type: "line",
          silent: true,
          shape: { x1: x + 9.5, y1: y + 5, x2: x + 14, y2: y + 5 },
          style: { stroke: C.danger, lineWidth: 1, opacity },
        });
      }
      if (lifecycleState === "liquidating" || lifecycleState === "terminated") {
        elements.push({
          type: "line",
          silent: true,
          shape: { x1: x + 9.5, y1: y + 8, x2: x + 14, y2: y + 8 },
          style: { stroke: lifecycleState === "liquidating" ? C.danger : C.text, lineWidth: 1, opacity },
        });
      }
    });

    chart.setOption({ graphic: { elements } }, { replaceMerge: ["graphic"], lazyUpdate: true });
  }, [spotlightIds, tickId, zoomLevel]);

  useEffect(() => {
    latestNodesRef.current = nodes;
    latestGraphNodesRef.current = graphNodes;
    latestSelectedAgentIdRef.current = selectedAgentId;
    latestLifecycleMapRef.current = agentLifecycleMap;
  }, [agentLifecycleMap, graphNodes, nodes, selectedAgentId]);

  useEffect(() => {
    latestOnHoverAgentRef.current = onHoverAgent;
    latestOnSelectAgentRef.current = onSelectAgent;
    latestOnSelectReasonRef.current = onSelectReason;
  }, [onHoverAgent, onSelectAgent, onSelectReason]);

  useEffect(() => {
    refreshGraphicOverlayRef.current = refreshGraphicOverlay;
  }, [refreshGraphicOverlay]);

  const scheduleGraphicOverlay = useCallback(() => {
    if (overlayTimerRef.current !== null) {
      window.clearTimeout(overlayTimerRef.current);
    }
    overlayTimerRef.current = window.setTimeout(() => {
      overlayTimerRef.current = null;
      window.requestAnimationFrame(() => refreshGraphicOverlayRef.current());
    }, 0);
  }, []);

  useEffect(() => {
    const host = chartHostRef.current;
    if (!host) return;
    const chart = echarts.init(host, undefined, { renderer: "canvas" });
    chartRef.current = chart;
    const handleClick = (params: unknown) => {
      const item = params as {
        dataType?: string;
        data?: Partial<ChartNodeDatum & ChartEdgeDatum>;
      };
      if (item.dataType === "node" && item.data?.agentId) {
        latestOnSelectAgentRef.current(item.data.agentId);
      }
      if (item.dataType === "edge") {
        latestOnSelectReasonRef.current(item.data?.reasonRef ?? null);
      }
    };
    const handleMouseOver = (params: unknown) => {
      const item = params as {
        dataType?: string;
        data?: Partial<ChartNodeDatum>;
      };
      if (item.dataType === "node" && item.data?.agentId) {
        latestOnHoverAgentRef.current(item.data.agentId);
      }
    };
    const handleMouseOut = (params: unknown) => {
      const item = params as { dataType?: string };
      if (item.dataType === "node") {
        latestOnHoverAgentRef.current(null);
      }
    };
    const handleRoam = () => {
      scheduleGraphicOverlay();
    };
    chart.on("click", handleClick);
    chart.on("mouseover", handleMouseOver);
    chart.on("mouseout", handleMouseOut);
    chart.on("graphRoam", handleRoam);
    const resizeObserver = new ResizeObserver(() => {
      chart.resize();
      scheduleGraphicOverlay();
    });
    resizeObserver.observe(host);
    return () => {
      if (overlayTimerRef.current !== null) {
        window.clearTimeout(overlayTimerRef.current);
        overlayTimerRef.current = null;
      }
      resizeObserver.disconnect();
      chart.off("click", handleClick);
      chart.off("mouseover", handleMouseOver);
      chart.off("mouseout", handleMouseOut);
      chart.off("graphRoam", handleRoam);
      chart.dispose();
      chartRef.current = null;
    };
  }, [scheduleGraphicOverlay]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || chart.isDisposed()) return;
    chart.setOption(option, { notMerge: true });
    scheduleGraphicOverlay();
  }, [option, scheduleGraphicOverlay]);

  const resetView = useCallback(() => {
    const chart = chartRef.current;
    setZoomLevel(1);
    onSelectReason(null);
    if (chart && !chart.isDisposed()) {
      chart.setOption({
        series: [{ id: GRAPH_SERIES_ID, center: [50, 50], zoom: 1 }],
      });
      scheduleGraphicOverlay();
    }
  }, [onSelectReason, scheduleGraphicOverlay]);

  const zoomBy = useCallback((direction: "in" | "out") => {
    setZoomLevel((current) => {
      const next =
        direction === "in"
          ? Math.min(3, current + GRAPH_ZOOM_STEP)
          : Math.max(0.45, current - GRAPH_ZOOM_STEP);
      return Number(next.toFixed(2));
    });
  }, []);

  return (
    <div className="topology panel">
      <div className="section-title">
        <span>推演画布</span>
        <div className="canvas-tools">
          <button type="button" onClick={() => onEdgeModeChange("current")}>当前 Tick</button>
          <button type="button" onClick={() => onEdgeModeChange("selected")}>选中链路</button>
          <button type="button" onClick={() => onEdgeModeChange("strong")}>高影响</button>
          <button type="button" onClick={resetView}>重置视图</button>
          <span className="zoom-controls">
            <button type="button" onClick={() => zoomBy("out")} title="缩小"><Minus size={14} /></button>
            <span className="zoom-level">{Math.round(zoomLevel * 100)}%</span>
            <button type="button" onClick={() => zoomBy("in")} title="放大"><Plus size={14} /></button>
            <button type="button" onClick={resetView} title="重置缩放"><Maximize2 size={14} /></button>
          </span>
        </div>
      </div>
      <div
        ref={chartHostRef}
        aria-label="推演拓扑图"
        className="topology-canvas topology-chart"
        role="img"
      />
    </div>
  );
}

function clampFinite(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function edgeCurveness(edge: AuditGraphEdge, index: number): number {
  const sign = (edge.source.charCodeAt(0) + edge.target.charCodeAt(0) + index) % 2 === 0 ? 1 : -1;
  return sign * (0.12 + (index % 3) * 0.04);
}

function formatEdgeWeight(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(2) : "0.00";
}

function watermarkText(text: string) {
  return {
    text,
    fill: "rgba(0,0,0,0.22)",
    font: "10px JetBrains Mono, Courier New, monospace",
  };
}
