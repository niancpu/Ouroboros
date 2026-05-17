import { memo, useEffect, useMemo, useRef } from "react";
import { BarChart, CandlestickChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import type { ComposeOption } from "echarts/core";
import type {
  BarSeriesOption,
  CandlestickSeriesOption,
} from "echarts/charts";
import type {
  GridComponentOption,
  TooltipComponentOption,
} from "echarts/components";
import type { OHLCVBar } from "../../utils/derive";
import { EmptyState } from "../common/EmptyState";

echarts.use([BarChart, CandlestickChart, GridComponent, TooltipComponent, CanvasRenderer]);

type ChartInstance = ReturnType<typeof echarts.init>;
type MarketChartOption = ComposeOption<
  GridComponentOption | TooltipComponentOption | CandlestickSeriesOption | BarSeriesOption
>;

interface MarketCurvesProps {
  bars: OHLCVBar[];
  lastPrice: number;
}

const C = {
  accent: "#0037c8",
  text: "#000000",
  secondary: "#2f2f2f",
  surface: "#ffffff",
} as const;

export const MarketCurves = memo(function MarketCurves({ bars, lastPrice }: MarketCurvesProps) {
  const chartHostRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ChartInstance | null>(null);
  const option = useMemo(() => buildOption(bars), [bars]);

  useEffect(() => {
    const host = chartHostRef.current;
    if (!host || bars.length === 0) return;
    const chart = echarts.init(host, undefined, { renderer: "canvas" });
    chartRef.current = chart;
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);

    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
      chartRef.current = null;
    };
  }, [bars.length]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || chart.isDisposed()) return;
    chart.setOption(option, { notMerge: true, lazyUpdate: true });
  }, [option]);

  if (bars.length === 0) {
    return (
      <div className="market-curves panel">
        <div className="section-title">
          <span>K线 / 成交量</span>
        </div>
        <EmptyState label="NO PRICE DATA" />
      </div>
    );
  }

  return (
    <div className="market-curves panel">
      <div className="section-title">
        <span>K线 / 成交量</span>
        <span className="market-price-readout">{safeNumber(lastPrice).toFixed(2)}</span>
      </div>
      <div ref={chartHostRef} className="market-chart" />
    </div>
  );
});

function buildOption(bars: OHLCVBar[]): MarketChartOption {
  const labels = bars.map((bar) => bar.tick_id);
  const candleData = bars.map((bar) => [bar.open, bar.close, bar.low, bar.high]);
  const volumeData = bars.map((bar) => ({
    value: bar.volume,
    itemStyle: { color: bar.close < bar.open ? C.text : C.surface, borderColor: C.text, borderWidth: 1 },
  }));
  const { min, max } = makePriceDomain(
    Math.min(...bars.map((bar) => bar.low)),
    Math.max(...bars.map((bar) => bar.high)),
    bars[bars.length - 1]?.close ?? 1,
  );

  return {
    animation: false,
    backgroundColor: C.surface,
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross", lineStyle: { color: C.accent, width: 1, type: "solid" } },
      borderColor: C.text,
      borderWidth: 1,
      backgroundColor: C.surface,
      padding: [6, 8],
      textStyle: {
        color: C.text,
        fontFamily: "JetBrains Mono, Courier New, monospace",
        fontSize: 11,
      },
      extraCssText: "box-shadow:none;border-radius:0;",
      formatter: (params) => formatTooltip(params, bars),
    },
    grid: [
      { left: 42, right: 12, top: 14, height: "52%", containLabel: false },
      { left: 42, right: 12, top: "72%", height: "18%", containLabel: false },
    ],
    xAxis: [
      buildXAxis(labels, 0, false),
      buildXAxis(labels, 1, true),
    ],
    yAxis: [
      {
        scale: true,
        min,
        max,
        splitNumber: 3,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: {
          color: C.secondary,
          fontFamily: "JetBrains Mono, Courier New, monospace",
          fontSize: 10,
          formatter: (value: number) => value.toFixed(2),
          margin: 6,
        },
        splitLine: { lineStyle: { color: C.text, width: 1, opacity: 0.18 } },
      },
      {
        gridIndex: 1,
        min: 0,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { show: false },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        type: "candlestick",
        name: "K",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: candleData,
        barWidth: "58%",
        itemStyle: {
          color: C.surface,
          color0: C.text,
          borderColor: C.text,
          borderColor0: C.text,
          borderWidth: 1,
        },
        emphasis: { disabled: true },
      },
      {
        type: "bar",
        name: "V",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volumeData,
        barWidth: "58%",
        emphasis: { disabled: true },
      },
    ],
  };
}

function buildXAxis(labels: string[], gridIndex: number, showLabels: boolean) {
  return {
    type: "category" as const,
    data: labels,
    gridIndex,
    boundaryGap: true,
    axisLine: { lineStyle: { color: C.text, width: 1 } },
    axisTick: { show: false },
    axisLabel: {
      show: showLabels,
      color: C.secondary,
      fontFamily: "JetBrains Mono, Courier New, monospace",
      fontSize: 10,
      interval: labels.length > 12 ? Math.ceil(labels.length / 6) - 1 : 1,
      margin: 6,
    },
    splitLine: { show: false },
  };
}

function formatTooltip(params: unknown, bars: ReadonlyArray<OHLCVBar>) {
  if (!Array.isArray(params)) return "";
  const first = params[0] as { dataIndex?: number } | undefined;
  const bar = typeof first?.dataIndex === "number" ? bars[first.dataIndex] : null;
  if (!bar) return "";

  return [
    `[${bar.tick_id}]`,
    `O ${bar.open.toFixed(2)}  H ${bar.high.toFixed(2)}`,
    `L ${bar.low.toFixed(2)}  C ${bar.close.toFixed(2)}`,
    `V ${bar.volume.toLocaleString("en-US")}`,
  ].join("<br/>");
}

function makePriceDomain(minValue: number, maxValue: number, fallbackPrice: number) {
  const anchor = Math.max(Math.abs(safeNumber(fallbackPrice, maxValue || 1)), 1);
  const rawRange = Math.max(maxValue - minValue, 0);
  const visibleRange = Math.max(rawRange, anchor * 0.012);
  const padding = visibleRange * 0.2;
  const center = rawRange > 0 ? (minValue + maxValue) / 2 : anchor;

  return {
    min: center - visibleRange / 2 - padding,
    max: center + visibleRange / 2 + padding,
  };
}

function safeNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}
