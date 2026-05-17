interface StepperProps {
  label: string;
  value: number;
  onMinus: () => void;
  onPlus: () => void;
}

export function Stepper({ label, value, onMinus, onPlus }: StepperProps) {
  return (
    <div className="stepper-row">
      <span>{label}</span>
      <div className="stepper-control">
        <button type="button" onClick={onMinus} aria-label={`${label}减少`}>
          -
        </button>
        <output>{value}</output>
        <button type="button" onClick={onPlus} aria-label={`${label}增加`}>
          +
        </button>
      </div>
    </div>
  );
}
