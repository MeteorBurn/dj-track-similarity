import { Minus, Plus } from "lucide-react";

// Shared by the analysis panel and the SONARA settings dialog: a bounded
// integer field with +/- steppers instead of the native number spinner.
export function NumberStepper({
  label,
  value,
  minimum,
  maximum,
  disabled,
  classPrefix,
  onChange,
}: {
  label: string;
  value: number;
  minimum: number;
  maximum: number;
  disabled: boolean;
  classPrefix: string;
  onChange: (value: number) => void;
}) {
  const update = (value: number) => onChange(
    Math.min(maximum, Math.max(minimum, Math.trunc(value) || minimum)),
  );
  return (
    <div className="worker-control">
      <span>{label}</span>
      <div className="stepper">
        <button className={`icon-button number-stepper-decrement-button ${classPrefix}-decrement-button`} title={`Уменьшить ${label}`} disabled={disabled || value <= minimum} onClick={() => update(value - 1)} type="button"><Minus size={15} /></button>
        <input type="number" min={minimum} max={maximum} value={value} disabled={disabled} onChange={(event) => update(Number(event.target.value))} />
        <button className={`icon-button number-stepper-increment-button ${classPrefix}-increment-button`} title={`Увеличить ${label}`} disabled={disabled || value >= maximum} onClick={() => update(value + 1)} type="button"><Plus size={15} /></button>
      </div>
    </div>
  );
}
