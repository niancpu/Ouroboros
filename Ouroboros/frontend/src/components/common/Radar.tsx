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
      <circle cx="50" cy="50" r="34" fill="none" stroke="currentColor" strokeWidth="0.35" strokeDasharray="2 2" opacity={0.6} />
      <circle cx="50" cy="50" r="22" fill="none" stroke="currentColor" strokeWidth="0.35" opacity={0.4} />
      <line x1="50" y1="12" x2="50" y2="88" stroke="currentColor" strokeWidth="0.3" opacity={0.35} />
      <line x1="12" y1="50" x2="88" y2="50" stroke="currentColor" strokeWidth="0.3" opacity={0.35} />
      <polyline points={`${points} ${points.split(" ")[0]}`} fill="none" stroke="var(--color-accent, #1e3a5f)" strokeWidth="1.2" />
      <circle cx="50" cy="16" r="1.5" fill="var(--color-accent, #1e3a5f)" />
      <text x="52" y="18" fontSize="4" fill="var(--color-accent, #1e3a5f)">[N1]</text>
      <text x="16" y="46" fontSize="4" fill="var(--color-accent, #1e3a5f)">[N2]</text>
      <text x="48" y="88" fontSize="4" fill="var(--color-accent, #1e3a5f)">[N3]</text>
      <text x="76" y="46" fontSize="4" fill="var(--color-accent, #1e3a5f)">[N4]</text>
    </svg>
  );
}

function safeNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}
