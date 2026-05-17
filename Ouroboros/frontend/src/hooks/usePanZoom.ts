import { useCallback, useEffect, useRef, useState } from "react";

interface ViewBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

const DEFAULT_VIEWBOX: ViewBox = { x: 0, y: 0, w: 100, h: 100 };
const MIN_ZOOM = 0.05;
const MAX_ZOOM = 30;
const DRAG_THRESHOLD_PX = 4;

export function usePanZoom() {
  const [viewBox, setViewBox] = useState<ViewBox>(DEFAULT_VIEWBOX);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const viewBoxRef = useRef<ViewBox>(DEFAULT_VIEWBOX);
  const isPanning = useRef(false);
  const dragStarted = useRef(false);
  const panStart = useRef({ x: 0, y: 0 });
  const downPos = useRef({ x: 0, y: 0 });

  useEffect(() => {
    viewBoxRef.current = viewBox;
  }, [viewBox]);

  const applyZoom = useCallback((deltaY: number, clientX: number, clientY: number) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const prev = viewBoxRef.current;
    const factor = Math.exp(deltaY * 0.0015);
    const nextW = Math.min(Math.max(prev.w * factor, 100 / MAX_ZOOM), 100 / MIN_ZOOM);
    const nextH = Math.min(Math.max(prev.h * factor, 100 / MAX_ZOOM), 100 / MIN_ZOOM);
    const sx = (clientX - rect.left) / rect.width;
    const sy = (clientY - rect.top) / rect.height;
    const nextX = prev.x + sx * (prev.w - nextW);
    const nextY = prev.y + sy * (prev.h - nextH);
    setViewBox({ x: nextX, y: nextY, w: nextW, h: nextH });
  }, []);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const handler = (e: WheelEvent) => {
      e.preventDefault();
      applyZoom(e.deltaY, e.clientX, e.clientY);
    };
    svg.addEventListener("wheel", handler, { passive: false });
    return () => {
      svg.removeEventListener("wheel", handler);
    };
  }, [applyZoom]);

  const onPointerDown = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    if (e.button !== 0) return;
    isPanning.current = true;
    dragStarted.current = false;
    panStart.current = { x: e.clientX, y: e.clientY };
    downPos.current = { x: e.clientX, y: e.clientY };
    (e.currentTarget as SVGSVGElement).setPointerCapture(e.pointerId);
  }, []);

  const onPointerMove = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    if (!isPanning.current) return;
    const svg = svgRef.current;
    if (!svg) return;
    if (!dragStarted.current) {
      const dxAbs = Math.abs(e.clientX - downPos.current.x);
      const dyAbs = Math.abs(e.clientY - downPos.current.y);
      if (dxAbs < DRAG_THRESHOLD_PX && dyAbs < DRAG_THRESHOLD_PX) return;
      dragStarted.current = true;
    }
    const rect = svg.getBoundingClientRect();
    const prev = viewBoxRef.current;
    const dx = ((e.clientX - panStart.current.x) / rect.width) * prev.w;
    const dy = ((e.clientY - panStart.current.y) / rect.height) * prev.h;
    panStart.current = { x: e.clientX, y: e.clientY };
    setViewBox({ x: prev.x - dx, y: prev.y - dy, w: prev.w, h: prev.h });
  }, []);

  const onPointerUp = useCallback((e: React.PointerEvent<SVGSVGElement>) => {
    if (!isPanning.current) return;
    isPanning.current = false;
    try {
      (e.currentTarget as SVGSVGElement).releasePointerCapture(e.pointerId);
    } catch {
      /* pointer may already be released */
    }
  }, []);

  const onClickCapture = useCallback((e: React.MouseEvent<SVGSVGElement>) => {
    if (dragStarted.current) {
      e.stopPropagation();
      e.preventDefault();
      dragStarted.current = false;
    }
  }, []);

  const resetView = useCallback(() => {
    setViewBox(DEFAULT_VIEWBOX);
  }, []);

  const zoomBy = useCallback((deltaY: number) => {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    applyZoom(deltaY, rect.left + rect.width / 2, rect.top + rect.height / 2);
  }, [applyZoom]);

  const viewBoxStr = `${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`;
  const zoomLevel = 100 / viewBox.w;

  return {
    svgRef,
    viewBoxStr,
    zoomLevel,
    onPointerDown,
    onPointerMove,
    onPointerUp,
    onClickCapture,
    resetView,
    zoomBy,
  };
}
