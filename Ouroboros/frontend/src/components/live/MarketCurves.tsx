import { memo } from "react";
import { Activity } from "lucide-react";
import type { OHLCVBar } from "../../utils/derive";
import { EmptyState } from "../common/EmptyState";

interface MarketCurvesProps {
  bars: OHLCVBar[];
  lastPrice: number;
}

export const MarketCurves = memo(function MarketCurves({ bars, lastPrice }: MarketCurvesProps) {
  if (bars.length === 0) {
    return (
      <div className="market-curves panel">
        <div className="section-title">
          <Activity size={16} />
          <span>K线 / 成交量</span>
        </div>
        <EmptyState label="NO PRICE DATA" />
      </div>
    );
  }

  const n = bars.length;
  // SVG layout: total 100×100 viewBox, top 65% for candles, bottom 35% for volume
  const CANDLE_TOP = 2;
  const CANDLE_BOT = 62;
  const VOL_TOP = 66;
  const VOL_BOT = 98;
  const PADDING = 1; // left/right padding

  const slotW = (100 - PADDING * 2) / n;
  const candleW = Math.max(slotW * 0.55, 0.6);

  const allHighs = bars.map((b) => b.high);
  const allLows = bars.map((b) => b.low);
  const priceMax = safeMax(allHighs, safeNumber(lastPrice));
  const priceMin = safeMin(allLows, safeNumber(lastPrice));
  const priceRange = Math.max(priceMax - priceMin, 0.01);

  const maxVol = Math.max(safeMax(bars.map((b) => safeNumber(b.volume)), 1), 1);

  function toY(price: number, top: number, bot: number, min: number, range: number) {
    return bot - ((price - min) / range) * (bot - top);
  }

  const candleH = CANDLE_BOT - CANDLE_TOP;
  const volH = VOL_BOT - VOL_TOP;

  return (
    <div className="market-curves panel">
      <div className="section-title">
        <Activity size={16} />
        <span>K线 / 成交量</span>
        <span style={{ marginLeft: "auto", fontSize: 12, fontFamily: "'JetBrains Mono', 'Courier New', monospace" }}>
          {safeNumber(lastPrice).toFixed(2)}
        </span>
      </div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none">
        {/* Axis lines */}
        <line x1={PADDING} y1={CANDLE_BOT} x2={100 - PADDING} y2={CANDLE_BOT} stroke="var(--color-border, #e5e7eb)" strokeWidth="0.3" />
        <line x1={PADDING} y1={VOL_BOT} x2={100 - PADDING} y2={VOL_BOT} stroke="var(--color-border, #e5e7eb)" strokeWidth="0.3" />

        {bars.map((bar, i) => {
          const cx = PADDING + i * slotW + slotW / 2;
          const openY = toY(bar.open, CANDLE_TOP, CANDLE_BOT, priceMin, priceRange);
          const closeY = toY(bar.close, CANDLE_TOP, CANDLE_BOT, priceMin, priceRange);
          const highY = toY(bar.high, CANDLE_TOP, CANDLE_BOT, priceMin, priceRange);
          const lowY = toY(bar.low, CANDLE_TOP, CANDLE_BOT, priceMin, priceRange);

          const bodyTop = Math.min(openY, closeY);
          const bodyH = Math.max(Math.abs(closeY - openY), 0.5);

          // A股涨跌色规则：红=涨，绿=跌，黑=平
          const color = bar.close > bar.open ? "var(--color-danger, #b91c1c)" : bar.close < bar.open ? "var(--color-success, #047857)" : "var(--color-text-primary, #1a1a2e)";

          // Volume bar
          const volBarH = Math.max((safeNumber(bar.volume) / maxVol) * volH, 0.4);
          const volY = VOL_BOT - volBarH;

          return (
            <g key={bar.tick_id}>
              {/* Wick */}
              <line x1={cx} y1={highY} x2={cx} y2={lowY} stroke={color} strokeWidth="0.4" />
              {/* Body */}
              <rect
                x={cx - candleW / 2}
                y={bodyTop}
                width={candleW}
                height={bodyH}
                fill={color}
                stroke={color}
                strokeWidth="0.2"
              />
              {/* Volume bar */}
              <rect
                x={cx - candleW / 2}
                y={volY}
                width={candleW}
                height={volBarH}
                fill={color}
                opacity={0.7}
              />
            </g>
          );
        })}

        {/* Price labels */}
        <text x={PADDING + 0.5} y={CANDLE_TOP + 3.5} fontSize="3" fill="var(--color-text-secondary, #6b7280)" fontFamily="'JetBrains Mono', 'Courier New', monospace">
          {priceMax.toFixed(2)}
        </text>
        <text x={PADDING + 0.5} y={CANDLE_BOT - 1} fontSize="3" fill="var(--color-text-secondary, #6b7280)" fontFamily="'JetBrains Mono', 'Courier New', monospace">
          {priceMin.toFixed(2)}
        </text>
      </svg>
    </div>
  );
});

function safeNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function safeMax(values: ReadonlyArray<number>, fallback: number): number {
  const finite = values.filter((value) => Number.isFinite(value));
  return finite.length > 0 ? Math.max(...finite) : fallback;
}

function safeMin(values: ReadonlyArray<number>, fallback: number): number {
  const finite = values.filter((value) => Number.isFinite(value));
  return finite.length > 0 ? Math.min(...finite) : fallback;
}
