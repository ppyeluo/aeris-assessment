/**
 * Variant resolution — pure functions, no React.
 *
 * Keeping this logic out of the components is what makes the interesting cases
 * (impossible combination, sold-out combination, quantity clamp) testable
 * without rendering anything.
 */

import type { Product, Sku } from '../api/types';

/** Chosen value per dimension; a dimension is undecided until it has a value. */
export type Selection = Record<string, string | undefined>;

export type OptionState =
  | 'available' // a purchasable SKU exists for this value
  | 'out_of_stock' // the combination exists but has no stock
  | 'impossible'; // no SKU exists for this combination

/** SKUs consistent with every dimension decided so far. */
export function candidatesFor(product: Product, selection: Selection): Sku[] {
  return product.skus.filter((sku) =>
    product.options.every((dimension) => {
      const chosen = selection[dimension.name];
      return chosen === undefined || sku.option_values[dimension.name] === chosen;
    }),
  );
}

/** The single SKU for a fully decided selection, if the combination exists. */
export function resolveSku(product: Product, selection: Selection): Sku | undefined {
  const complete = product.options.every((dimension) => selection[dimension.name] !== undefined);
  if (!complete) return undefined;
  return product.skus.find((sku) =>
    product.options.every((dimension) => sku.option_values[dimension.name] === selection[dimension.name]),
  );
}

/**
 * State of one option value, evaluated against the *other* current choices.
 * A value is only "available" when at least one reachable SKU has stock, so a
 * shopper can never pick their way into an unbuyable combination.
 */
export function optionState(
  product: Product,
  selection: Selection,
  dimensionName: string,
  value: string,
): OptionState {
  const matches = candidatesFor(product, { ...selection, [dimensionName]: value });
  if (matches.length === 0) return 'impossible';
  return matches.some((sku) => sku.available > 0) ? 'available' : 'out_of_stock';
}

/**
 * Highest quantity the shopper may order, or ``0`` when there is nothing to order
 * (no SKU resolved, or its stock is exhausted). The server is the final authority.
 */
export function maxQuantity(sku: Sku | undefined, hardLimit = 100): number {
  if (!sku) return 0;
  return Math.min(sku.available, hardLimit);
}

/** Clamp ``value`` into ``1..maxQuantity``; when that range is empty the result is 0. */
export function clampQuantity(value: number, sku: Sku | undefined, hardLimit = 100): number {
  const ceiling = maxQuantity(sku, hardLimit);
  if (ceiling <= 0) return 0;
  if (!Number.isFinite(value)) return 1;
  return Math.min(Math.max(Math.trunc(value), 1), ceiling);
}

export function formatPrice(cents: number, currency: string): string {
  return new Intl.NumberFormat('en-AU', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
  }).format(cents / 100);
}

export function stockLabel(sku: Sku | undefined, selectionComplete: boolean): string {
  if (!selectionComplete) return 'Select a colour and size';
  if (!sku) return 'This combination is not available';
  if (sku.available === 0) return 'Sold out';
  if (sku.available <= 3) return `Only ${sku.available} left`;
  return 'In stock';
}
