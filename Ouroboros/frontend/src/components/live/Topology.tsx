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
  AgentType,
  AuditGraphPayload,
  LifecycleState,
} from "../../types/api";
import { agentTypeLabels, labelFrom, riskStateLabels } from "../../i18n/labels";
import { displayAgentName, formatPercent, formatTick } from "../../utils/format";
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
const LABEL_MAX_ZOOM_SCALE = 3.5;
const LABEL_MIN_ZOOM_SCALE = 0.65;
const LABEL_BASE_FONT_SIZE = 11;

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
  symbol: "circle" | "rect" | "roundRect" | "triangle" | "diamond" | "pin";
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
  const latestVisualNodesRef = useRef<VisualNode[]>([]);
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
          symbol: "diamond",
          symbolSize: 14,
          itemStyle: {
            color: "#efefef",
            borderColor: C.secondary,
            borderWidth: 1.3,
            opacity: 0.94,
          },
        };
      }

      const node = visualNode.node;
      const visual = agentTypeVisual(node.agent_type);
      const lifecycleState = agentLifecycleMap.get(node.agent_id);
      const isSelected = node.agent_id === selectedAgentId;
      const isDimmed = spotlightIds ? !spotlightIds.has(node.agent_id) : false;
      const isBlue = isSelected || node.belief_score >= 0.6 || node.risk_state === "warning";
      const stroke =
        lifecycleState === "margin_call" || lifecycleState === "liquidating"
          ? C.danger
          : isBlue
            ? C.accent
            : visual.borderColor;
      return {
        id: node.agent_id,
        name: displayAgentName(node.agent_id),
        nodeKind: "agent",
        agentId: node.agent_id,
        x: node.x,
        y: node.y,
        value: clampFinite(node.belief_score, 0),
        sanitizedTooltip: [
          node.agent_id,
          labelFrom(agentTypeLabels, node.agent_type),
          labelFrom(riskStateLabels, node.risk_state),
          `信念 ${node.belief_score.toFixed(2)}`,
          `持仓 ${formatPercent(positionExposure(node, graphNodes))}`,
        ].join(" / "),
        symbol: visual.symbol,
        symbolSize: visual.size,
        itemStyle: {
          color: visual.fillColor,
          borderColor: stroke,
          borderWidth: isSelected ? 2.4 : visual.borderWidth,
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
            return `${item.data?.publicReason ?? "公开原因"}<br/>权重 ${formatEdgeWeight(item.data?.weight)}`;
          }
          return item.data?.sanitizedTooltip ?? "";
        },
      },
      series: [
        {
          id: GRAPH_SERIES_ID,
          type: "graph",
          layout: "none",
          roam: false,
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
    const labelScale = overlayLabelScale(graphView.zoom);
    const labelFont = overlayLabelFont(LABEL_BASE_FONT_SIZE, labelScale);
    const overlayStrokeWidth = overlayLineWidth(labelScale);
    const sourceOffset = 12 * labelScale;
    const agentElbowOffset = 20 * labelScale;
    const agentLabelOffset = 6 * labelScale;
    const agentTextYOffset = 7 * labelScale;
    const overlay = new echarts.graphic.Group({ silent: true });
    overlay.add(new echarts.graphic.Text({
      x: 12,
      y: 12,
      silent: true,
      style: watermarkText(`缩放 ${graphView.zoom.toFixed(2)} 倍`),
    }));
    overlay.add(new echarts.graphic.Text({
      x: Math.max(12, width - 184),
      y: Math.max(20, height - 18),
      silent: true,
      style: watermarkText(`节拍 ${formatTick(tickId)} / 推演图谱`),
    }));

    latestVisualNodesRef.current.forEach((visualNode) => {
      const pixel = chart.convertToPixel({ seriesId: GRAPH_SERIES_ID }, [visualNode.x, visualNode.y]);
      if (!Array.isArray(pixel)) return;
      const [x, y] = pixel;
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;

      if (visualNode.kind === "source") {
        const labelRight = x < width - 96 * labelScale;
        overlay.add(new echarts.graphic.Text({
          silent: true,
          x: labelRight ? x + sourceOffset : x - sourceOffset,
          y: y - 13 * labelScale,
          style: {
            text: sourceLabel(visualNode.id),
            fill: C.secondary,
            font: labelFont,
            align: labelRight ? "left" : "right",
            verticalAlign: "middle",
          },
        }));
        return;
      }

      const node = visualNode.node;
      const allNodes = latestGraphNodesRef.current;
      const lifecycleState = latestLifecycleMapRef.current.get(node.agent_id);
      const isSelected = node.agent_id === latestSelectedAgentIdRef.current;
      const exposure = positionExposure(node, allNodes);
      const labelRight = x < width - 172 * labelScale;
      const elbowX = labelRight ? x + agentElbowOffset : x - agentElbowOffset;
      const labelX = labelRight ? elbowX + agentLabelOffset : elbowX - agentLabelOffset;
      const labelY = Math.max(18 * labelScale, Math.min(height - 18 * labelScale, y - 14 * labelScale));
      const dimmed = spotlightIds && !spotlightIds.has(node.agent_id);
      const opacity = dimmed ? 0.1 : 1;
      const typeLabel = labelFrom(agentTypeLabels, node.agent_type);
      const riskLabel = labelFrom(riskStateLabels, node.risk_state);
      const displayName = displayAgentName(node.agent_id);

      if (isSelected) {
        const selectionSize = 24 * labelScale;
        overlay.add(new echarts.graphic.Rect({
          silent: true,
          shape: { x: x - selectionSize / 2, y: y - selectionSize / 2, width: selectionSize, height: selectionSize },
          style: {
            fill: "transparent",
            stroke: C.text,
            lineDash: [4, 3],
            lineWidth: overlayStrokeWidth,
            opacity,
          },
        }));
      }

      overlay.add(
        new echarts.graphic.Line({
          silent: true,
          shape: {
            x1: x - 5.5 * labelScale,
            y1: y + 6.4 * labelScale,
            x2: x - 5.5 * labelScale + exposure * 11 * labelScale,
            y2: y + 6.4 * labelScale,
          },
          style: { stroke: C.text, lineWidth: overlayStrokeWidth, opacity },
        }),
      );
      overlay.add(
        new echarts.graphic.Polyline({
          silent: true,
          shape: {
            points: [
              [x + (labelRight ? 9 : -9) * labelScale, y],
              [elbowX, y],
              [elbowX, labelY],
            ],
          },
          style: { stroke: C.text, fill: "transparent", lineWidth: overlayStrokeWidth, opacity },
        }),
      );
      overlay.add(
        new echarts.graphic.Text({
          silent: true,
          x: labelX,
          y: labelY - agentTextYOffset,
          style: {
            text: `${displayName} ${typeLabel} 信念${node.belief_score.toFixed(2)} 持仓${formatPercent(exposure)} ${riskLabel}`,
            fill: dimmed ? "rgba(0,0,0,0.1)" : C.secondary,
            font: labelFont,
            align: labelRight ? "left" : "right",
            verticalAlign: "middle",
          },
        }),
      );

      if (lifecycleState === "margin_call" || lifecycleState === "liquidating") {
        overlay.add(new echarts.graphic.Line({
          silent: true,
          shape: {
            x1: x + 9.5 * labelScale,
            y1: y + 5 * labelScale,
            x2: x + 14 * labelScale,
            y2: y + 5 * labelScale,
          },
          style: { stroke: C.danger, lineWidth: overlayStrokeWidth, opacity },
        }));
      }
      if (lifecycleState === "liquidating" || lifecycleState === "terminated") {
        overlay.add(new echarts.graphic.Line({
          silent: true,
          shape: {
            x1: x + 9.5 * labelScale,
            y1: y + 8 * labelScale,
            x2: x + 14 * labelScale,
            y2: y + 8 * labelScale,
          },
          style: {
            stroke: lifecycleState === "liquidating" ? C.danger : C.text,
            lineWidth: overlayStrokeWidth,
            opacity,
          },
        }));
      }
    });

    zr.add(overlay);
    overlayGroupRef.current = overlay;
  }, [spotlightIds, tickId, graphView.zoom]);

  useEffect(() => {
    latestVisualNodesRef.current = visualNodes;
    latestGraphNodesRef.current = graphNodes;
    latestSelectedAgentIdRef.current = selectedAgentId;
    latestLifecycleMapRef.current = agentLifecycleMap;
  }, [agentLifecycleMap, graphNodes, selectedAgentId, visualNodes]);

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
    const resizeChart = () => {
      chart.resize({
        width: host.clientWidth,
        height: host.clientHeight,
      });
      scheduleGraphicOverlay();
    };
    const applyChartView = (view: GraphView) => {
      const nextView = normalizeGraphView(view);
      setGraphViewState(nextView, graphViewRef, setGraphView);
      chart.setOption({
        series: [{ id: GRAPH_SERIES_ID, center: nextView.center, zoom: nextView.zoom }],
      }, { lazyUpdate: true });
      scheduleGraphicOverlay();
    };
    const zoomChart = (zoom: number) => {
      const currentView = readGraphView(chart) ?? graphViewRef.current;
      applyChartView({ ...currentView, zoom });
    };
    const panChartBy = (deltaX: number, deltaY: number) => {
      const currentView = readGraphView(chart) ?? graphViewRef.current;
      const anchor: [number, number] = [host.clientWidth / 2, host.clientHeight / 2];
      const anchorData = pixelToDataPoint(chart, anchor);
      const shiftedData = pixelToDataPoint(chart, [anchor[0] + deltaX, anchor[1] + deltaY]);
      if (!anchorData || !shiftedData) return;
      applyChartView({
        ...currentView,
        center: [
          currentView.center[0] - (shiftedData[0] - anchorData[0]),
          currentView.center[1] - (shiftedData[1] - anchorData[1]),
        ],
      });
    };
    const pointers = new Map<number, { x: number; y: number; pointerType: string }>();
    let mouseDragPoint: { x: number; y: number } | null = null;
    let touchDragPoint: { x: number; y: number } | null = null;
    let pinchStart: { distance: number; zoom: number } | null = null;
    const resetPinch = () => {
      pinchStart = null;
      touchDragPoint = null;
      if (pointers.size === 1) {
        const [point] = [...pointers.values()];
        touchDragPoint = { x: point.x, y: point.y };
      }
    };
    const handleWheel = (event: WheelEvent) => {
      event.preventDefault();
      const currentView = readGraphView(chart) ?? graphViewRef.current;
      const factor = Math.exp(-event.deltaY * 0.0016);
      zoomChart(currentView.zoom * factor);
    };
    const handlePointerDown = (event: PointerEvent) => {
      if (event.pointerType === "mouse") {
        if (event.button !== 0) return;
        mouseDragPoint = { x: event.clientX, y: event.clientY };
        host.setPointerCapture(event.pointerId);
        return;
      }
      event.preventDefault();
      pointers.set(event.pointerId, {
        x: event.clientX,
        y: event.clientY,
        pointerType: event.pointerType,
      });
      host.setPointerCapture(event.pointerId);
      if (pointers.size === 1) {
        touchDragPoint = { x: event.clientX, y: event.clientY };
      }
      if (pointers.size === 2) {
        const points = [...pointers.values()];
        pinchStart = {
          distance: pointDistance(points[0], points[1]),
          zoom: (readGraphView(chart) ?? graphViewRef.current).zoom,
        };
      }
    };
    const handlePointerMove = (event: PointerEvent) => {
      if (event.pointerType === "mouse") {
        if (!mouseDragPoint || (event.buttons & 1) !== 1) return;
        event.preventDefault();
        panChartBy(event.clientX - mouseDragPoint.x, event.clientY - mouseDragPoint.y);
        mouseDragPoint = { x: event.clientX, y: event.clientY };
        return;
      }
      if (!pointers.has(event.pointerId)) return;
      event.preventDefault();
      pointers.set(event.pointerId, {
        x: event.clientX,
        y: event.clientY,
        pointerType: event.pointerType,
      });
      if (pointers.size >= 2) {
        const points = [...pointers.values()];
        const distance = pointDistance(points[0], points[1]);
        if (!pinchStart || pinchStart.distance <= 0) {
          pinchStart = {
            distance,
            zoom: (readGraphView(chart) ?? graphViewRef.current).zoom,
          };
          return;
        }
        zoomChart(pinchStart.zoom * (distance / pinchStart.distance));
        return;
      }
      if (touchDragPoint) {
        panChartBy(event.clientX - touchDragPoint.x, event.clientY - touchDragPoint.y);
      }
      touchDragPoint = { x: event.clientX, y: event.clientY };
    };
    const handlePointerEnd = (event: PointerEvent) => {
      if (event.pointerType === "mouse") {
        mouseDragPoint = null;
      } else {
        pointers.delete(event.pointerId);
        resetPinch();
      }
      if (host.hasPointerCapture(event.pointerId)) {
        host.releasePointerCapture(event.pointerId);
      }
    };
    chart.on("click", handleClick);
    chart.on("mouseover", handleMouseOver);
    chart.on("mouseout", handleMouseOut);
    chart.on("graphRoam", handleRoam);
    host.addEventListener("wheel", handleWheel, { passive: false });
    host.addEventListener("pointerdown", handlePointerDown);
    host.addEventListener("pointermove", handlePointerMove);
    host.addEventListener("pointerup", handlePointerEnd);
    host.addEventListener("pointercancel", handlePointerEnd);
    let resizeTimer: number | null = null;
    window.requestAnimationFrame(resizeChart);
    const resizeObserver = new ResizeObserver(() => {
      if (resizeTimer !== null) {
        window.clearTimeout(resizeTimer);
      }
      resizeTimer = window.setTimeout(() => {
        resizeTimer = null;
        if (chart.isDisposed()) return;
        resizeChart();
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
      host.removeEventListener("wheel", handleWheel);
      host.removeEventListener("pointerdown", handlePointerDown);
      host.removeEventListener("pointermove", handlePointerMove);
      host.removeEventListener("pointerup", handlePointerEnd);
      host.removeEventListener("pointercancel", handlePointerEnd);
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
          <button type="button" onClick={() => onEdgeModeChange("current")}>当前节拍</button>
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
            当前节拍只有智能体状态，还没有公开事件、信念变化或交易影响形成的关系链路。
          </div>
        )}
      </div>
    </div>
  );
}

function clampFinite(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function pointDistance(a: { x: number; y: number }, b: { x: number; y: number }): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function pixelToDataPoint(
  chart: ChartInstance,
  pixel: [number, number],
): [number, number] | null {
  const converted = chart.convertFromPixel({ seriesId: GRAPH_SERIES_ID }, pixel);
  if (!Array.isArray(converted) || converted.length < 2) return null;
  const x = clampFinite(converted[0], NaN);
  const y = clampFinite(converted[1], NaN);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  return [x, y];
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

function overlayLabelScale(zoom: number): number {
  const finiteZoom = Number.isFinite(zoom) ? zoom : GRAPH_DEFAULT_VIEW.zoom;
  return Math.max(LABEL_MIN_ZOOM_SCALE, Math.min(LABEL_MAX_ZOOM_SCALE, finiteZoom));
}

function overlayLabelFont(baseSize: number, scale: number): string {
  return `${formatCssPx(baseSize * scale)} Helvetica Neue, Arial, PingFang SC, sans-serif`;
}

function overlayLineWidth(scale: number): number {
  return Math.max(1, Math.min(1.6, scale));
}

function formatCssPx(value: number): string {
  return `${Number(value.toFixed(2))}px`;
}

function agentTypeVisual(agentType: AgentType): {
  symbol: ChartNodeDatum["symbol"];
  size: number;
  fillColor: string;
  borderColor: string;
  borderWidth: number;
} {
  if (agentType === "mutual_fund") {
    return {
      symbol: "rect",
      size: 18,
      fillColor: "#e8f0ff",
      borderColor: "#0037c8",
      borderWidth: 1.4,
    };
  }
  if (agentType === "hot_money") {
    return {
      symbol: "triangle",
      size: 18,
      fillColor: "#fff0d8",
      borderColor: "#9a3412",
      borderWidth: 1.4,
    };
  }
  if (agentType === "quant_algo") {
    return {
      symbol: "diamond",
      size: 17,
      fillColor: "#e7f7ef",
      borderColor: "#047857",
      borderWidth: 1.4,
    };
  }
  if (agentType === "national_team") {
    return {
      symbol: "pin",
      size: 19,
      fillColor: "#ffe8e8",
      borderColor: "#b91c1c",
      borderWidth: 1.4,
    };
  }
  if (agentType === "institution") {
    return {
      symbol: "roundRect",
      size: 18,
      fillColor: "#f1ecff",
      borderColor: "#5b21b6",
      borderWidth: 1.4,
    };
  }
  if (agentType === "retail_cluster") {
    return {
      symbol: "roundRect",
      size: 17,
      fillColor: "#f3f3f3",
      borderColor: "#2f2f2f",
      borderWidth: 1.3,
    };
  }
  return {
    symbol: "circle",
    size: 16,
    fillColor: C.surface,
    borderColor: C.text,
    borderWidth: 1.2,
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
