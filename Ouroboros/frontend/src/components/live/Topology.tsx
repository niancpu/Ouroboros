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
import { Minus, Maximize2, Minimize2, Plus } from "lucide-react";
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
  agentOnlyGraphEdges,
  aggregatePositionShare,
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
type VisualNodeKind = "agent";

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
const LABEL_MAX_ZOOM_SCALE = 1.2;
const LABEL_MIN_ZOOM_SCALE = 0.85;
const LABEL_BASE_FONT_SIZE = 11;
const LABEL_VIEWPORT_MARGIN = 24;
const NODE_DRAG_MIN_DISTANCE = 3;

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
  const topologyRef = useRef<HTMLDivElement | null>(null);
  const chartHostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ChartInstance | null>(null);
  const latestVisualNodesRef = useRef<VisualNode[]>([]);
  const latestSelectedAgentIdRef = useRef<string | null>(null);
  const latestOnHoverAgentRef = useRef(onHoverAgent);
  const latestOnSelectAgentRef = useRef(onSelectAgent);
  const latestOnSelectReasonRef = useRef(onSelectReason);
  const refreshGraphicOverlayRef = useRef<() => void>(() => {});
  const overlayTimerRef = useRef<number | null>(null);
  const overlayGroupRef = useRef<OverlayGroup | null>(null);
  const uiCallbackTimersRef = useRef<number[]>([]);
  const graphViewRef = useRef<GraphView>(GRAPH_DEFAULT_VIEW);
  const nodePositionOverridesRef = useRef<Map<string, NodePoint>>(new Map());
  const [graphView, setGraphView] = useState<GraphView>(GRAPH_DEFAULT_VIEW);
  const [nodePositionOverrides, setNodePositionOverrides] = useState<Map<string, NodePoint>>(() => new Map());
  const [isFullscreen, setIsFullscreen] = useState(false);

  const graphNodes: AuditGraphNode[] = useMemo(
    () => (graph.nodes.length ? [...graph.nodes] : fallbackNodesFromAgents(agents))
      .sort((a, b) => a.agent_id.localeCompare(b.agent_id)),
    [agents, graph.nodes],
  );
  const nodes: TopologyNode[] = graphNodes.map((node) => {
    const point = deterministicNodePoint(stableNodeIndex(node.agent_id), graphNodes.length);
    const override = nodePositionOverrides.get(node.agent_id);
    return {
      ...node,
      belief_score: clampFinite(node.belief_score, 0),
      position_value: clampFinite(node.position_value, 0),
      risk_state: node.risk_state,
      ...(override ?? point),
    };
  });
  const agentEdges = useMemo(
    () => agentOnlyGraphEdges(graph.edges, graphNodes),
    [graph.edges, graphNodes],
  );
  const visibleEdges = pruneGraphEdges(agentEdges, selectedAgentId, edgeMode);
  const spotlightIds = buildSpotlightIds(hoveredAgentId, agentEdges);
  const visualNodes = useMemo(
    () => buildVisualNodes(nodes),
    [nodes],
  );
  const visualNodeById = useMemo(
    () => new Map(visualNodes.map((node) => [node.id, node])),
    [visualNodes],
  );
  const option = useMemo(() => {
    const chartNodes: ChartNodeDatum[] = visualNodes.map((visualNode) => {
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
          `总持仓占比 ${formatPercent(aggregatePositionShare(node, graphNodes))}`,
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
    const agentNameOffset = 13 * labelScale;
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
      if (!isLabelAnchorVisible(x, y, width, height)) return;

      const node = visualNode.node;
      const isSelected = node.agent_id === latestSelectedAgentIdRef.current;
      const labelRight = x < width - 120 * labelScale;
      const labelX = labelRight ? x + agentNameOffset : x - agentNameOffset;
      const dimmed = spotlightIds && !spotlightIds.has(node.agent_id);
      const opacity = dimmed ? 0.1 : 1;
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
          shape: { x1: x + (labelRight ? 7 : -7) * labelScale, y1: y, x2: labelX - (labelRight ? 4 : -4) * labelScale, y2: y },
          style: { stroke: C.text, lineWidth: overlayStrokeWidth, opacity },
        }),
      );
      overlay.add(
        new echarts.graphic.Text({
          silent: true,
          x: labelX,
          y,
          style: {
            text: displayName,
            fill: dimmed ? "rgba(0,0,0,0.1)" : C.secondary,
            font: labelFont,
            align: labelRight ? "left" : "right",
            verticalAlign: "middle",
          },
        }),
      );
    });

    zr.add(overlay);
    overlayGroupRef.current = overlay;
  }, [spotlightIds, tickId, graphView.zoom]);

  useEffect(() => {
    latestVisualNodesRef.current = visualNodes;
    latestSelectedAgentIdRef.current = selectedAgentId;
  }, [selectedAgentId, visualNodes]);

  useEffect(() => {
    nodePositionOverridesRef.current = nodePositionOverrides;
  }, [nodePositionOverrides]);

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
    const handleFullscreenChange = () => {
      const nextIsFullscreen = document.fullscreenElement === topologyRef.current;
      setIsFullscreen(nextIsFullscreen);
      window.requestAnimationFrame(() => {
        const host = chartHostRef.current;
        const chart = chartRef.current;
        if (!host || !chart || chart.isDisposed()) return;
        chart.resize({
          width: host.clientWidth,
          height: host.clientHeight,
        });
        scheduleGraphicOverlay();
      });
    };

    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => {
      document.removeEventListener("fullscreenchange", handleFullscreenChange);
    };
  }, [scheduleGraphicOverlay]);

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
    let suppressNextClick = false;
    const handleClick = (params: unknown) => {
      if (suppressNextClick) {
        suppressNextClick = false;
        return;
      }
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
    const resizeChart = () => {
      chart.resize({
        width: host.clientWidth,
        height: host.clientHeight,
      });
      const currentView = graphViewRef.current;
      chart.setOption({
        series: [{ id: GRAPH_SERIES_ID, center: currentView.center, zoom: currentView.zoom }],
      }, { lazyUpdate: true });
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
      const currentView = graphViewRef.current;
      applyChartView({ ...currentView, zoom });
    };
    const panChartBy = (deltaX: number, deltaY: number) => {
      const currentView = graphViewRef.current;
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
    let nodeDrag: {
      id: string;
      pointerId: number;
      pointerType: string;
      startClientX: number;
      startClientY: number;
      offset: [number, number];
      moved: boolean;
    } | null = null;
    const moveNodeTo = (id: string, point: NodePoint) => {
      const nextOverrides = new Map(nodePositionOverridesRef.current);
      nextOverrides.set(id, point);
      nodePositionOverridesRef.current = nextOverrides;
      setNodePositionOverrides(nextOverrides);
      scheduleGraphicOverlay();
    };
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
      const currentView = graphViewRef.current;
      const factor = Math.exp(-event.deltaY * 0.0016);
      zoomChart(currentView.zoom * factor);
    };
    const handlePointerDown = (event: PointerEvent) => {
      const hostPixel = clientToHostPixel(host, event.clientX, event.clientY);
      const hitNode = findVisualNodeAtPixel(chart, latestVisualNodesRef.current, hostPixel);
      if (event.pointerType === "mouse") {
        if (event.button !== 0) return;
        if (hitNode) {
          const pointerData = pixelToDataPoint(chart, hostPixel);
          if (!pointerData) return;
          nodeDrag = {
            id: hitNode.id,
            pointerId: event.pointerId,
            pointerType: event.pointerType,
            startClientX: event.clientX,
            startClientY: event.clientY,
            offset: [hitNode.x - pointerData[0], hitNode.y - pointerData[1]],
            moved: false,
          };
          host.setPointerCapture(event.pointerId);
          return;
        }
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
      if (hitNode && pointers.size === 1) {
        const pointerData = pixelToDataPoint(chart, hostPixel);
        if (pointerData) {
          nodeDrag = {
            id: hitNode.id,
            pointerId: event.pointerId,
            pointerType: event.pointerType,
            startClientX: event.clientX,
            startClientY: event.clientY,
            offset: [hitNode.x - pointerData[0], hitNode.y - pointerData[1]],
            moved: false,
          };
        }
      }
      if (pointers.size === 1) {
        touchDragPoint = { x: event.clientX, y: event.clientY };
      }
      if (pointers.size === 2) {
        nodeDrag = null;
        const points = [...pointers.values()];
        pinchStart = {
          distance: pointDistance(points[0], points[1]),
          zoom: graphViewRef.current.zoom,
        };
      }
    };
    const handlePointerMove = (event: PointerEvent) => {
      if (nodeDrag?.pointerId === event.pointerId) {
        event.preventDefault();
        const pointerData = pixelToDataPoint(chart, clientToHostPixel(host, event.clientX, event.clientY));
        if (!pointerData) return;
        const movedDistance = Math.hypot(event.clientX - nodeDrag.startClientX, event.clientY - nodeDrag.startClientY);
        nodeDrag.moved = nodeDrag.moved || movedDistance >= NODE_DRAG_MIN_DISTANCE;
        moveNodeTo(nodeDrag.id, {
          x: pointerData[0] + nodeDrag.offset[0],
          y: pointerData[1] + nodeDrag.offset[1],
        });
        return;
      }
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
            zoom: graphViewRef.current.zoom,
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
      if (nodeDrag?.pointerId === event.pointerId) {
        const draggedNode = nodeDrag;
        suppressNextClick = draggedNode.moved;
        nodeDrag = null;
        if (!draggedNode.moved) {
          deferUiCallback(() => latestOnSelectAgentRef.current(draggedNode.id));
        }
      }
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
      host.removeEventListener("wheel", handleWheel);
      host.removeEventListener("pointerdown", handlePointerDown);
      host.removeEventListener("pointermove", handlePointerMove);
      host.removeEventListener("pointerup", handlePointerEnd);
      host.removeEventListener("pointercancel", handlePointerEnd);
      chart.dispose();
      chartRef.current = null;
    };
  }, [deferUiCallback, scheduleGraphicOverlay]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || chart.isDisposed()) return;
    chart.setOption(option, { notMerge: true });
    scheduleGraphicOverlay();
  }, [option, scheduleGraphicOverlay]);

  const resetView = useCallback(() => {
    const chart = chartRef.current;
    setGraphViewState(GRAPH_DEFAULT_VIEW, graphViewRef, setGraphView);
    nodePositionOverridesRef.current = new Map();
    setNodePositionOverrides(new Map());
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
    const currentView = graphViewRef.current;
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

  const toggleFullscreen = useCallback(() => {
    const root = topologyRef.current;
    if (!root) return;
    if (document.fullscreenElement === root) {
      void document.exitFullscreen().catch(() => undefined);
      return;
    }
    void root.requestFullscreen().catch(() => undefined);
  }, []);

  return (
    <div className="topology panel" ref={topologyRef}>
      <div className="section-title">
        <div className="section-title-main">
          <span>推演画布</span>
          <span className={visibleEdges.length ? "graph-health" : "graph-health muted"}>
            {visibleEdges.length ? `${visibleEdges.length} 条 Agent 关系` : "暂无 Agent 关系"}
          </span>
        </div>
        <div className="canvas-tools">
          <button type="button" onClick={() => onEdgeModeChange("current")}>当前节拍</button>
          <button type="button" onClick={() => onEdgeModeChange("selected")}>选中链路</button>
          <button type="button" onClick={() => onEdgeModeChange("strong")}>高影响</button>
          <button type="button" onClick={resetView}>重置视图</button>
          <span className="zoom-controls">
            <button type="button" onClick={() => zoomBy("out")} title="缩小"><Minus size={14} /></button>
            <span className="zoom-level">{Math.round(graphView.zoom * 100)}%</span>
            <button type="button" onClick={() => zoomBy("in")} title="放大"><Plus size={14} /></button>
            <button
              aria-label={isFullscreen ? "退出图谱全屏" : "图谱全屏"}
              type="button"
              onClick={toggleFullscreen}
              title={isFullscreen ? "退出图谱全屏" : "图谱全屏"}
            >
              {isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            </button>
          </span>
        </div>
      </div>
      <div className="topology-canvas" aria-label="推演拓扑图" role="img">
        <div ref={chartHostRef} className="topology-chart" />
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

function clientToHostPixel(host: HTMLElement, clientX: number, clientY: number): [number, number] {
  const rect = host.getBoundingClientRect();
  return [clientX - rect.left, clientY - rect.top];
}

function findVisualNodeAtPixel(
  chart: ChartInstance,
  visualNodes: ReadonlyArray<VisualNode>,
  pixel: [number, number],
): VisualNode | null {
  let matchedNode: VisualNode | null = null;
  let matchedDistance = Infinity;
  for (const visualNode of visualNodes) {
    const nodePixel = chart.convertToPixel({ seriesId: GRAPH_SERIES_ID }, [visualNode.x, visualNode.y]);
    if (!Array.isArray(nodePixel) || nodePixel.length < 2) continue;
    const distance = Math.hypot(pixel[0] - clampFinite(nodePixel[0], 0), pixel[1] - clampFinite(nodePixel[1], 0));
    const radius = agentTypeVisual(visualNode.node.agent_type).size / 2 + 8;
    if (distance <= radius && distance < matchedDistance) {
      matchedNode = visualNode;
      matchedDistance = distance;
    }
  }
  return matchedNode;
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

function stableNodeIndex(agentId: string): number {
  let hash = 0;
  for (let index = 0; index < agentId.length; index += 1) {
    hash = (hash * 31 + agentId.charCodeAt(index)) >>> 0;
  }
  return hash;
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

function isLabelAnchorVisible(x: number, y: number, width: number, height: number): boolean {
  return (
    x >= -LABEL_VIEWPORT_MARGIN &&
    x <= width + LABEL_VIEWPORT_MARGIN &&
    y >= -LABEL_VIEWPORT_MARGIN &&
    y <= height + LABEL_VIEWPORT_MARGIN
  );
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

type VisualNode = VisualAgentNode;

function buildVisualNodes(agentNodes: ReadonlyArray<TopologyNode>): VisualNode[] {
  return agentNodes.map((node) => ({
    id: node.agent_id,
    kind: "agent",
    node,
    x: node.x,
    y: node.y,
  }));
}
