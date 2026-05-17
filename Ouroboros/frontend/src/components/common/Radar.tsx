interface RadarProps {
  values: number[];
}

export function Radar({ values }: RadarProps) {
  const max = Math.max(...values, 10);
  const points = values
    .map((value, index) => {
      const angle = -Math.PI / 2 + (index * Math.PI * 2) / values.length;
      const radius = 34 * (value / max);
      return `${50 + Math.cos(angle) * radius},${50 + Math.sin(angle) * radius}`;
    })
    .join(" ");

  return (
    <svg className="radar" viewBox="0 0 100 100" role="img" aria-label="智能体参数雷达图">
      <polygon points="50,16 84,50 50,84 16,50" fill="none" stroke="currentColor" strokeWidth="1" />
      <polygon points="50,28 72,50 50,72 28,50" fill="none" stroke="currentColor" strokeWidth="1" />
      <polyline points={`${points} ${points.split(" ")[0]}`} fill="none" stroke="#002fa7" strokeWidth="1.5" />
    </svg>
  );
}
