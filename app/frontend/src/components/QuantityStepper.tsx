interface Props {
  value: number;
  max: number;
  disabled?: boolean;
  onChange: (value: number) => void;
}

/** Quantity control bounded by the selected SKU's availability. */
export function QuantityStepper({ value, max, disabled = false, onChange }: Props) {
  return (
    <div className="quantity">
      <span className="quantity-label" id="quantity-label">
        Quantity
      </span>
      <div className="quantity-controls">
        <button
          type="button"
          aria-label="Decrease quantity"
          onClick={() => onChange(value - 1)}
          disabled={disabled || value <= 1}
        >
          −
        </button>
        <input
          type="number"
          inputMode="numeric"
          // With nothing purchasable selected the value is 0, so the floor follows
          // it rather than contradicting it with min=1 > max=0.
          min={max > 0 ? 1 : 0}
          max={max}
          value={value}
          disabled={disabled}
          aria-labelledby="quantity-label"
          onChange={(event) => onChange(Number(event.target.value))}
        />
        <button
          type="button"
          aria-label="Increase quantity"
          onClick={() => onChange(value + 1)}
          disabled={disabled || value >= max}
        >
          +
        </button>
      </div>
      {max > 0 && <span className="quantity-hint">{max} available</span>}
    </div>
  );
}
