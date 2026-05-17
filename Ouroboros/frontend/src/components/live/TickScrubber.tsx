interface TickScrubberProps {
  ticks: string[];
  currentIndex: number;
  onChange: (index: number) => void;
}

export function TickScrubber({ ticks, currentIndex, onChange }: TickScrubberProps) {
  const visibleMarks = ticks.filter((_, index) => {
    if (index === 0) return true;
    if (index === currentIndex) return true;
    if (index === ticks.length - 1) return true;
    if (ticks.length <= 10) return true;
    return index % 5 === 0;
  });

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
        {visibleMarks.map((tick) => {
          const index = ticks.indexOf(tick);
          return (
            <span className={index === currentIndex ? "active" : ""} key={tick} title={tick}>
              T{index}
            </span>
          );
        })}
      </div>
    </div>
  );
}
