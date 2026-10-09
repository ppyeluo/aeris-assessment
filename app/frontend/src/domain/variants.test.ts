import { describe, expect, it } from 'vitest';

import type { Product } from '../api/types';
import {
  candidatesFor,
  clampQuantity,
  formatPrice,
  maxQuantity,
  optionState,
  resolveSku,
  stockLabel,
} from './variants';

/**
 * Fixture mirrors the seeded catalogue's interesting shapes:
 * an out-of-stock combination (Black/M) and a missing one (White/M).
 */
const product: Product = {
  id: 'tee',
  name: 'Tee',
  description: '',
  currency: 'AUD',
  image: '/images/tee-black.svg',
  options: [
    { name: 'Colour', values: ['Black', 'White'] },
    { name: 'Size', values: ['S', 'M'] },
  ],
  skus: [
    {
      id: 'black-s',
      option_values: { Colour: 'Black', Size: 'S' },
      price_cents: 3900,
      stock: 2,
      available: 2,
      image: '/images/tee-black.svg',
    },
    {
      id: 'black-m',
      option_values: { Colour: 'Black', Size: 'M' },
      price_cents: 3900,
      stock: 0,
      available: 0,
      image: '/images/tee-black.svg',
    },
    {
      id: 'white-s',
      option_values: { Colour: 'White', Size: 'S' },
      price_cents: 4200,
      stock: 1,
      available: 1,
      image: '/images/tee-white.svg',
    },
  ],
};

describe('resolveSku', () => {
  it('resolves a fully chosen combination', () => {
    expect(resolveSku(product, { Colour: 'Black', Size: 'S' })?.id).toBe('black-s');
  });

  it('returns undefined while a dimension is undecided', () => {
    expect(resolveSku(product, { Colour: 'Black' })).toBeUndefined();
    expect(resolveSku(product, {})).toBeUndefined();
  });

  it('returns undefined for a combination that has no SKU', () => {
    expect(resolveSku(product, { Colour: 'White', Size: 'M' })).toBeUndefined();
  });
});

describe('optionState', () => {
  it('marks a value available when a purchasable SKU exists', () => {
    expect(optionState(product, {}, 'Size', 'S')).toBe('available');
  });

  it('marks a stockless value as out_of_stock', () => {
    expect(optionState(product, { Colour: 'Black' }, 'Size', 'M')).toBe('out_of_stock');
  });

  it('marks a combination with no SKU as impossible', () => {
    expect(optionState(product, { Size: 'M' }, 'Colour', 'White')).toBe('impossible');
  });

  it('reacts to the other dimension already chosen', () => {
    // With nothing chosen, Black is fine; with Size=M chosen, Black is sold out.
    expect(optionState(product, {}, 'Colour', 'Black')).toBe('available');
    expect(optionState(product, { Size: 'M' }, 'Colour', 'Black')).toBe('out_of_stock');
  });
});

describe('candidatesFor', () => {
  it('ignores undecided dimensions', () => {
    expect(candidatesFor(product, {})).toHaveLength(3);
    expect(candidatesFor(product, { Colour: 'Black' }).map((sku) => sku.id)).toEqual([
      'black-s',
      'black-m',
    ]);
  });
});

describe('quantity helpers', () => {
  it('clamps to the available stock', () => {
    const sku = product.skus[0]!;
    expect(maxQuantity(sku)).toBe(2);
    expect(clampQuantity(5, sku)).toBe(2);
    expect(clampQuantity(0, sku)).toBe(1);
    expect(clampQuantity(Number.NaN, sku)).toBe(1);
  });

  it('caps at the hard limit when stock is plentiful', () => {
    const sku = { ...product.skus[0]!, available: 500 };
    expect(maxQuantity(sku)).toBe(100);
    expect(clampQuantity(500, sku)).toBe(100);
  });

  it('returns the available stock rather than a floor of one', () => {
    const soldOut = product.skus[1]!; // available: 0
    expect(maxQuantity(soldOut)).toBe(0);
    expect(clampQuantity(5, soldOut)).toBe(0);
  });

  it('returns zero when no SKU is resolved', () => {
    expect(maxQuantity(undefined)).toBe(0);
    expect(clampQuantity(3, undefined)).toBe(0);
  });
});

describe('formatting', () => {
  it('formats cents as AUD', () => {
    expect(formatPrice(3900, 'AUD')).toBe('$39.00');
  });

  it('describes stock states in the UI copy', () => {
    expect(stockLabel(undefined, false)).toBe('Select a colour and size');
    expect(stockLabel(undefined, true)).toBe('This combination is not available');
    expect(stockLabel(product.skus[1]!, true)).toBe('Sold out');
    expect(stockLabel(product.skus[2]!, true)).toBe('Only 1 left');
    expect(stockLabel(product.skus[0]!, true)).toBe('Only 2 left');
  });
});
