import { memo } from "react";
import { Activity } from "lucide-react";
import type { MarketSnapshot } from "../../types/api";
import { EmptyState } from "../common/EmptyState";

interface MarketCurvesProps {
  market: MarketSnapshot;
  priceHistory: number[];
}

export function MarketCurves({ market, priceHistory }: MarketCurvesProps) {
  if (priceHistory.length === 0) {
    return (
      <div className="market-curves panel">
        <div className="section-title">
          <Activity size={16} />
          <span>价格 / 共识曲线</span>
        </div>
        <EmptyState label="NO PRICE HISTORY" />
      </div>
    );
  }

  const min = Math.min(...priceHistory);
  const max = Math.max(...priceHistory);
  const points = priceHistory
    .map((price, index) => {
      const x = (index / Math.max(priceHistory.length - 1, 1)) * 96 + 2;
      const y = 88 - ((price - min) / Math.max(max - min, 0.01)) * 76;
      return `${x},${y}`;
    })
    .join(" ");

  return (
    <div className="market-curves panel">
      <div className="section-title">
        <Activity size={16} />
        <span>价格 / 共识曲线</span>
      </div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none">
        <polyline points={points} fill="none" stroke="#002fa7" strokeWidth="1.6" />
        <line x1="2" y1="52" x2="98" y2="44" stroke="#000" strokeWidth="0.8" />
        <text x="3" y="12" fontSize="4" fill="#000">
          高点 {max.toFixed(2)}
        </text>
        <text x="3" y="94" fontSize="4" fill="#000">
          低点 {min.toFixed(2)}
        </text>
        <text x="72" y="14" fontSize="4" fill="#002fa7">
          最新 {market.last_price.toFixed(2)}
        </text>
      </svg>
    </div>
  );
}
