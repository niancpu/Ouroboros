import type { CausalChain } from "../../types/webApi";
import { causalStepTypeLabels, labelFrom } from "../../i18n/labels";

interface DossierPathProps {
  chains: CausalChain[];
}

export function DossierPath({ chains }: DossierPathProps) {
  const steps = chains[0]?.steps ?? [];
  return (
    <svg
      className="dossier-path"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      role="img"
      aria-label="因果路径"
    >
      {steps.map((step, index) => (
        <g key={step.step_id}>
          <rect
            x={6 + index * 22}
            y={22 + (index % 2) * 24}
            width="16"
            height="10"
            fill="#fff"
            stroke="#000"
          />
          <text x={7 + index * 22} y={29 + (index % 2) * 24} fontSize="3">
            {labelFrom(causalStepTypeLabels, step.step_type)}
          </text>
          {index < steps.length - 1 && (
            <path
              d={`M ${22 + index * 22} ${27 + (index % 2) * 24} C ${
                29 + index * 22
              } ${8 + (index % 2) * 24}, ${35 + index * 22} ${
                66 - (index % 2) * 24
              }, ${50 + index * 22} ${27 + ((index + 1) % 2) * 24}`}
              fill="none"
              stroke={index === 1 ? "#002fa7" : "#000"}
              strokeWidth="0.9"
            />
          )}
        </g>
      ))}
    </svg>
  );
}
