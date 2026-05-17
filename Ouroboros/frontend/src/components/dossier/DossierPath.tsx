import type { CausalChain } from "../../types/webApi";
import { causalStepTypeLabels, labelFrom } from "../../i18n/labels";

interface DossierPathProps {
  chains: CausalChain[];
  selectedChainId?: string | null;
  selectedTickId?: string | null;
}

export function DossierPath({ chains, selectedChainId, selectedTickId }: DossierPathProps) {
  const selectedChain = chains.find((chain) => chain.chain_id === selectedChainId) ?? chains[0];
  const steps = selectedChain?.steps ?? [];
  const stepGap = steps.length > 1 ? 84 / Math.max(steps.length - 1, 1) : 0;

  return (
    <div className="dossier-path-frame">
      <svg
        className="dossier-path"
        viewBox="0 0 100 100"
        preserveAspectRatio="none"
        role="img"
        aria-label="因果路径"
      >
        {steps.map((step, index) => {
          const x = steps.length > 1 ? 8 + index * stepGap : 42;
          const y = 24 + (index % 2) * 34;
          const isSelectedTick = selectedTickId === step.tick_id;
          const next = steps[index + 1];
          const nextX = next ? 8 + (index + 1) * stepGap : x;
          const nextY = 24 + ((index + 1) % 2) * 34;
          const lineSelected = Boolean(
            selectedChain?.chain_id === selectedChainId ||
              isSelectedTick ||
              (next && selectedTickId === next.tick_id),
          );

          return (
            <g key={step.step_id}>
              {next && (
                <polyline
                  points={`${x + 12},${y + 6} ${x + 18},${y + 6} ${nextX - 6},${nextY + 6} ${nextX},${nextY + 6}`}
                  fill="none"
                  stroke={lineSelected ? "var(--color-accent, #0037c8)" : "#000000"}
                  strokeWidth={lineSelected ? "1.2" : "0.7"}
                />
              )}
              <rect
                x={x}
                y={y}
                width="12"
                height="12"
                fill="#ffffff"
                stroke={isSelectedTick ? "var(--color-accent, #0037c8)" : "#000000"}
                strokeWidth={isSelectedTick ? "1.2" : "0.8"}
              />
              <text x={x + 1.2} y={y + 5} fontSize="2.4">
                {labelFrom(causalStepTypeLabels, step.step_type)}
              </text>
              <text x={x + 1.2} y={y + 9} fontSize="2.2">
                {step.tick_id}
              </text>
            </g>
          );
        })}
      </svg>
      {selectedChain && (
        <div className="dossier-path-caption">
          <strong>{selectedChain.title}</strong>
          <span>{selectedChain.summary}</span>
        </div>
      )}
    </div>
  );
}
