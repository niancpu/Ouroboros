interface RadarProps {
  values: number[];
}

export function Radar({ values }: RadarProps) {
  const cleanedValues = values.map((value) => safeNumber(value));
  const max = Math.max(...cleanedValues, 10);
  const points = values
    .map((value, index) => {
      const angle = -Math.PI / 2 + (index * Math.PI * 2) / values.length;
      const radius = 34 * (safeNumber(value) / max);
      return `${50 + Math.cos(angle) * radius},${50 + Math.sin(angle) * radius}`;
    })
    .join(" ");

  return (
    <svg className="radar" viewBox="0 0 100 100" role="img" aria-label="智能体参数雷达图">
      <polygon points="50,16 84,50 50,84 16,50" fill="none" stroke="currentColor" strokeWidth="0.5" opacity={0.3} />
      <polygon points="50,28 72,50 50,72 28,50" fill="none" stroke="currentColor" strokeWidth="0.5" opacity={0.3} />
      <polygon points={`${points} ${points.split(" ")[0]}`} fill="var(--color-accent, #1e3a5f)" fillOpacity="0.1" stroke="none" />
      <polyline points={`${points} ${points.split(" ")[0]}`} fill="none" stroke="var(--color-accent, #1e3a5f)" strokeWidth="1.2" />
    </svg>
  );
}

function safeNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}
