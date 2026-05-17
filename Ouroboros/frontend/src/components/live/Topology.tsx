import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type MutableRefObject,
  type SetStateAction,
} from "react";
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
type OverlayGroup = InstanceType<typeof echarts.graphic.Group>;
type VisualNodeKind = "agent" | "source";

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
const GRAPH_MIN_ZOOM = 0.15;
const GRAPH_MAX_ZOOM = 8;
const GRAPH_DEFAULT_CENTER: [number, number] = [50, 50];
const GRAPH_DEFAULT_VIEW: GraphView = { zoom: 1, center: GRAPH_DEFAULT_CENTER };

const C = {
  accent: "#0037c8",
  danger: "#b91c1c",
  text: "#000000",
  secondary: "#2f2f2f",
  surface: "#ffffff",
} as const;

type TopologyNode = AuditGraphNode & NodePoint;

interface GraphView {
  zoom: number;
  center: [number, number];
}

interface ChartNodeDatum {
  id: string;
  name: string;
  nodeKind: VisualNodeKind;
  agentId?: string;
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
  const overlayGroupRef = useRef<OverlayGroup | null>(null);
  const uiCallbackTimersRef = useRef<number[]>([]);
  const graphViewRef = useRef<GraphView>(GRAPH_DEFAULT_VIEW);
  const [graphView, setGraphView] = useState<GraphView>(GRAPH_DEFAULT_VIEW);

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
  const visibleEdges = pruneGraphEdges(graph.edges, selectedAgentId, edgeMode);
  const spotlightIds = buildSpotlightIds(hoveredAgentId, graph.edges);
  const visualNodes = useMemo(
    () => buildVisualNodes(nodes, visibleEdges),
    [nodes, visibleEdges],
  );
  const visualNodeById = useMemo(
    () => new Map(visualNodes.map((node) => [node.id, node])),
    [visualNodes],
  );
  const option = useMemo(() => {
    const chartNodes: ChartNodeDatum[] = visualNodes.map((visualNode) => {
      if (visualNode.kind === "source") {
        return {
          id: visualNode.id,
          name: sourceLabel(visualNode.id),
          nodeKind: "source",
          x: visualNode.x,
          y: visualNode.y,
          value: 0,
          sanitizedTooltip: `${sourceLabel(visualNode.id)} / 公开来源`,
          symbol: "circle",
          symbolSize: 11,
          itemStyle: {
            color: "#f6f6f6",
            borderColor: C.secondary,
            borderWidth: 1,
            opacity: 0.86,
          },
        };
      }

      const node = visualNode.node;
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
        nodeKind: "agent",
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
      if (!visualNodeById.has(edge.source) || !visualNodeById.has(edge.target)) return [];
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
          zoom: graphViewRef.current.zoom,
          center: graphViewRef.current.center,
          scaleLimit: {
            min: GRAPH_MIN_ZOOM,
            max: GRAPH_MAX_ZOOM,
          },
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
    selectedAgentId,
    selectedReasonRef,
    spotlightIds,
    visibleEdges,
    visualNodeById,
    visualNodes,
  ]);

  const refreshGraphicOverlay = useCallback(() => {
    const chart = chartRef.current;
    if (!chart || chart.isDisposed()) return;
    const zr = chart.getZr();
    if (overlayGroupRef.current) {
      zr.remove(overlayGroupRef.current);
      overlayGroupRef.current = null;
    }
    const width = chart.getWidth();
    const height = chart.getHeight();
    const overlay = new echarts.graphic.Group({ silent: true });
    overlay.add(new echarts.graphic.Text({
      x: 12,
      y: 12,
      silent: true,
      style: watermarkText(`X:-240.50 Y:112.00 // SCALE ${graphView.zoom.toFixed(2)}`),
    }));
    overlay.add(new echarts.graphic.Text({
      x: Math.max(12, width - 220),
      y: Math.max(20, height - 18),
      silent: true,
      style: watermarkText(`TICK ${formatTick(tickId)} // ECHARTS GRAPH`),
    }));

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
        overlay.add(new echarts.graphic.Rect({
          silent: true,
          shape: { x: x - 12, y: y - 12, width: 24, height: 24 },
          style: {
            fill: "transparent",
            stroke: C.text,
            lineDash: [4, 3],
            lineWidth: 1,
            opacity,
          },
        }));
      }

      overlay.add(
        new echarts.graphic.Line({
          silent: true,
          shape: { x1: x - 5.5, y1: y + 6.4, x2: x - 5.5 + exposure * 11, y2: y + 6.4 },
          style: { stroke: C.text, lineWidth: 1, opacity },
        }),
      );
      overlay.add(
        new echarts.graphic.Polyline({
          silent: true,
          shape: {
            points: [
              [x + (labelRight ? 9 : -9), y],
              [elbowX, y],
              [elbowX, labelY],
            ],
          },
          style: { stroke: C.text, fill: "transparent", lineWidth: 1, opacity },
        }),
      );
      overlay.add(
        new echarts.graphic.Text({
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
        }),
      );

      if (lifecycleState === "margin_call" || lifecycleState === "liquidating") {
        overlay.add(new echarts.graphic.Line({
          silent: true,
          shape: { x1: x + 9.5, y1: y + 5, x2: x + 14, y2: y + 5 },
          style: { stroke: C.danger, lineWidth: 1, opacity },
        }));
      }
      if (lifecycleState === "liquidating" || lifecycleState === "terminated") {
        overlay.add(new echarts.graphic.Line({
          silent: true,
          shape: { x1: x + 9.5, y1: y + 8, x2: x + 14, y2: y + 8 },
          style: { stroke: lifecycleState === "liquidating" ? C.danger : C.text, lineWidth: 1, opacity },
        }));
      }
    });

    zr.add(overlay);
    overlayGroupRef.current = overlay;
  }, [spotlightIds, tickId, graphView.zoom]);

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

  const syncGraphViewFromChart = useCallback((chart: ChartInstance) => {
    const nextView = readGraphView(chart);
    if (!nextView) return;
    setGraphViewState(nextView, graphViewRef, setGraphView);
  }, []);

  const deferUiCallback = useCallback((callback: () => void) => {
    const timer = window.setTimeout(() => {
      uiCallbackTimersRef.current = uiCallbackTimersRef.current.filter((item) => item !== timer);
      callback();
    }, 0);
    uiCallbackTimersRef.current.push(timer);
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
        const agentId = item.data.agentId;
        deferUiCallback(() => latestOnSelectAgentRef.current(agentId));
      }
      if (item.dataType === "edge") {
        const reasonRef = item.data?.reasonRef ?? null;
        deferUiCallback(() => latestOnSelectReasonRef.current(reasonRef));
      }
    };
    const handleMouseOver = (params: unknown) => {
      const item = params as {
        dataType?: string;
        data?: Partial<ChartNodeDatum>;
      };
      if (item.dataType === "node" && item.data?.agentId) {
        const agentId = item.data.agentId;
        deferUiCallback(() => latestOnHoverAgentRef.current(agentId));
      }
    };
    const handleMouseOut = (params: unknown) => {
      const item = params as { dataType?: string };
      if (item.dataType === "node") {
        deferUiCallback(() => latestOnHoverAgentRef.current(null));
      }
    };
    const handleRoam = () => {
      syncGraphViewFromChart(chart);
      scheduleGraphicOverlay();
    };
    chart.on("click", handleClick);
    chart.on("mouseover", handleMouseOver);
    chart.on("mouseout", handleMouseOut);
    chart.on("graphRoam", handleRoam);
    let resizeTimer: number | null = null;
    const resizeObserver = new ResizeObserver(() => {
      if (resizeTimer !== null) {
        window.clearTimeout(resizeTimer);
      }
      resizeTimer = window.setTimeout(() => {
        resizeTimer = null;
        if (chart.isDisposed()) return;
        chart.resize();
        scheduleGraphicOverlay();
      }, 0);
    });
    resizeObserver.observe(host);
    return () => {
      if (overlayTimerRef.current !== null) {
        window.clearTimeout(overlayTimerRef.current);
        overlayTimerRef.current = null;
      }
      if (resizeTimer !== null) {
        window.clearTimeout(resizeTimer);
        resizeTimer = null;
      }
      for (const timer of uiCallbackTimersRef.current) {
        window.clearTimeout(timer);
      }
      uiCallbackTimersRef.current = [];
      if (overlayGroupRef.current) {
        chart.getZr().remove(overlayGroupRef.current);
        overlayGroupRef.current = null;
      }
      resizeObserver.disconnect();
      chart.off("click", handleClick);
      chart.off("mouseover", handleMouseOver);
      chart.off("mouseout", handleMouseOut);
      chart.off("graphRoam", handleRoam);
      chart.dispose();
      chartRef.current = null;
    };
  }, [deferUiCallback, scheduleGraphicOverlay, syncGraphViewFromChart]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || chart.isDisposed()) return;
    chart.setOption(option, { notMerge: true });
    scheduleGraphicOverlay();
  }, [option, scheduleGraphicOverlay]);

  const resetView = useCallback(() => {
    const chart = chartRef.current;
    setGraphViewState(GRAPH_DEFAULT_VIEW, graphViewRef, setGraphView);
    onSelectReason(null);
    if (chart && !chart.isDisposed()) {
      chart.setOption({
        series: [{ id: GRAPH_SERIES_ID, center: GRAPH_DEFAULT_CENTER, zoom: 1 }],
      });
      scheduleGraphicOverlay();
    }
  }, [onSelectReason, scheduleGraphicOverlay]);

  const zoomBy = useCallback((direction: "in" | "out") => {
    const chart = chartRef.current;
    const currentView = readGraphView(chart) ?? graphViewRef.current;
    const nextZoom =
      direction === "in"
        ? Math.min(GRAPH_MAX_ZOOM, currentView.zoom + GRAPH_ZOOM_STEP)
        : Math.max(GRAPH_MIN_ZOOM, currentView.zoom - GRAPH_ZOOM_STEP);
    const nextView = { ...currentView, zoom: Number(nextZoom.toFixed(2)) };
    setGraphViewState(nextView, graphViewRef, setGraphView);
    if (chart && !chart.isDisposed()) {
      chart.setOption({
        series: [{ id: GRAPH_SERIES_ID, center: nextView.center, zoom: nextView.zoom }],
      });
      scheduleGraphicOverlay();
    }
  }, [scheduleGraphicOverlay]);

  return (
    <div className="topology panel">
      <div className="section-title">
        <span>推演画布</span>
        <span className={visibleEdges.length ? "graph-health" : "graph-health muted"}>
          {visibleEdges.length ? `${visibleEdges.length} 条关系` : "暂无关系链路"}
        </span>
        <div className="canvas-tools">
          <button type="button" onClick={() => onEdgeModeChange("current")}>当前 Tick</button>
          <button type="button" onClick={() => onEdgeModeChange("selected")}>选中链路</button>
          <button type="button" onClick={() => onEdgeModeChange("strong")}>高影响</button>
          <button type="button" onClick={resetView}>重置视图</button>
          <span className="zoom-controls">
            <button type="button" onClick={() => zoomBy("out")} title="缩小"><Minus size={14} /></button>
            <span className="zoom-level">{Math.round(graphView.zoom * 100)}%</span>
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
      >
        {visibleEdges.length === 0 && (
          <div className="topology-empty">
            当前 tick 只有智能体状态，还没有公开事件、信念变化或交易影响形成的关系链路。
          </div>
        )}
      </div>
    </div>
  );
}

function clampFinite(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function readGraphView(chart: ChartInstance | null): GraphView | null {
  if (!chart || chart.isDisposed()) return null;
  const option = chart.getOption() as {
    series?: Array<{
      id?: string;
      zoom?: unknown;
      center?: unknown;
    }>;
  };
  const series = option.series?.find((entry) => entry.id === GRAPH_SERIES_ID) ?? option.series?.[0];
  if (!series) return null;
  const zoom = typeof series.zoom === "number" && Number.isFinite(series.zoom)
    ? series.zoom
    : GRAPH_DEFAULT_VIEW.zoom;
  const center = Array.isArray(series.center) && series.center.length >= 2
    ? series.center
    : GRAPH_DEFAULT_CENTER;
  return {
    zoom: Number(Math.max(GRAPH_MIN_ZOOM, Math.min(GRAPH_MAX_ZOOM, zoom)).toFixed(2)),
    center: [
      clampFinite(center[0], GRAPH_DEFAULT_CENTER[0]),
      clampFinite(center[1], GRAPH_DEFAULT_CENTER[1]),
    ],
  };
}

function setGraphViewState(
  nextView: GraphView,
  graphViewRef: MutableRefObject<GraphView>,
  setGraphView: Dispatch<SetStateAction<GraphView>>,
): void {
  const normalizedView = normalizeGraphView(nextView);
  const current = graphViewRef.current;
  graphViewRef.current = normalizedView;
  if (
    current.zoom === normalizedView.zoom &&
    current.center[0] === normalizedView.center[0] &&
    current.center[1] === normalizedView.center[1]
  ) {
    return;
  }
  setGraphView(normalizedView);
}

function normalizeGraphView(view: GraphView): GraphView {
  return {
    zoom: Number(Math.max(GRAPH_MIN_ZOOM, Math.min(GRAPH_MAX_ZOOM, view.zoom)).toFixed(2)),
    center: [
      clampFinite(view.center[0], GRAPH_DEFAULT_CENTER[0]),
      clampFinite(view.center[1], GRAPH_DEFAULT_CENTER[1]),
    ],
  };
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

interface VisualAgentNode {
  id: string;
  kind: "agent";
  node: TopologyNode;
  x: number;
  y: number;
}

interface VisualSourceNode {
  id: string;
  kind: "source";
  x: number;
  y: number;
}

type VisualNode = VisualAgentNode | VisualSourceNode;

function buildVisualNodes(
  agentNodes: ReadonlyArray<TopologyNode>,
  edges: ReadonlyArray<AuditGraphEdge>,
): VisualNode[] {
  const visualNodes: VisualNode[] = agentNodes.map((node) => ({
    id: node.agent_id,
    kind: "agent",
    node,
    x: node.x,
    y: node.y,
  }));
  const agentIds = new Set(agentNodes.map((node) => node.agent_id));
  const sourceIds = new Set<string>();
  for (const edge of edges) {
    if (!agentIds.has(edge.source)) sourceIds.add(edge.source);
    if (!agentIds.has(edge.target)) sourceIds.add(edge.target);
  }
  [...sourceIds].forEach((id, index) => {
    const angle = -Math.PI / 2 + (index * Math.PI * 2) / Math.max(sourceIds.size, 1);
    visualNodes.push({
      id,
      kind: "source",
      x: 50 + Math.cos(angle) * 12,
      y: 50 + Math.sin(angle) * 10,
    });
  });
  return visualNodes;
}

function sourceLabel(id: string): string {
  if (id === "public_event") return "公开事件";
  if (id.startsWith("forum_") || id.startsWith("forum")) return "论坛消息";
  if (id.startsWith("mkt_") || id.startsWith("market")) return "行情事件";
  if (id.startsWith("tape_")) return "盘口异动";
  if (id.startsWith("news_")) return "新闻";
  return id;
}
