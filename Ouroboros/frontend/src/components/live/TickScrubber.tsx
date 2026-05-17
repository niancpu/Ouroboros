interface TickScrubberProps {
  ticks: string[];
  currentIndex: number;
  onChange: (index: number) => void;
}

export function TickScrubber({ ticks, currentIndex, onChange }: TickScrubberProps) {
  return (
    <div className="tick-scrubber">
      <input
        aria-label="Tick 时间刮擦器"
        max={Math.max(ticks.length - 1, 0)}
        min={0}
        onChange={(event) => onChange(Number(event.target.value))}
        step={1}
        type="range"
        value={currentIndex}
      />
      <div className="tick-marks">
        {ticks.map((tick, index) => (
          <span className={index === currentIndex ? "active" : ""} key={tick}>
            T{index}
          </span>
        ))}
      </div>
    </div>
  );
}
