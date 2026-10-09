import type { Product } from '../api/types';
import { optionState, type Selection } from '../domain/variants';

interface Props {
  product: Product;
  selection: Selection;
  disabled?: boolean;
  onSelect: (dimensionName: string, value: string) => void;
}

const STATE_NOTE: Record<string, string> = {
  out_of_stock: 'Sold out',
  impossible: 'Unavailable',
};

/**
 * Both dimensions rendered as radio groups: impossible combinations and
 * sold-out combinations are genuinely `disabled` (not merely styled), and the
 * reason is linked through `aria-describedby` so assistive tech announces it.
 */
export function OptionPicker({ product, selection, disabled = false, onSelect }: Props) {
  return (
    <>
      {product.options.map((dimension) => (
        <fieldset className="option-group" key={dimension.name}>
          <legend>{dimension.name}</legend>
          <div className="option-values">
            {dimension.values.map((value) => {
              const state = optionState(product, selection, dimension.name, value);
              const noteId = `note-${dimension.name}-${value}`.toLowerCase().replace(/\s+/g, '-');
              return (
                <label className="option" data-state={state} key={value}>
                  <input
                    type="radio"
                    name={dimension.name}
                    value={value}
                    checked={selection[dimension.name] === value}
                    disabled={disabled || state !== 'available'}
                    aria-label={value}
                    aria-describedby={state === 'available' ? undefined : noteId}
                    onChange={() => onSelect(dimension.name, value)}
                  />
                  <span className="option-value">{value}</span>
                  {state !== 'available' && (
                    <span className="option-note" id={noteId}>
                      {STATE_NOTE[state]}
                    </span>
                  )}
                </label>
              );
            })}
          </div>
        </fieldset>
      ))}
    </>
  );
}
