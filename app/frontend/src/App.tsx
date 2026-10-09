import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import * as defaultApi from './api/client';
import { ApiError } from './api/client';
import type { Cart, Product } from './api/types';
import { CartSummary } from './components/CartSummary';
import { OptionPicker } from './components/OptionPicker';
import { ProductImage } from './components/ProductImage';
import { QuantityStepper } from './components/QuantityStepper';
import {
  clampQuantity,
  formatPrice,
  maxQuantity,
  resolveSku,
  stockLabel,
  type Selection,
} from './domain/variants';

/** The slice of the HTTP client the page needs — injected so tests can fake it. */
export interface PdpApi {
  getProduct: typeof defaultApi.getProduct;
  getCart: typeof defaultApi.getCart;
  addToCart: typeof defaultApi.addToCart;
}

interface Props {
  productId: string;
  api?: PdpApi;
}

type LoadState = 'loading' | 'ready' | 'error';
type SubmitState = 'idle' | 'submitting' | 'success' | 'error';

function createIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `key-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function App({ productId, api = defaultApi }: Props) {
  const [product, setProduct] = useState<Product | null>(null);
  const [cart, setCart] = useState<Cart | null>(null);
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [loadError, setLoadError] = useState('');
  const [selection, setSelection] = useState<Selection>({});
  const [quantity, setQuantity] = useState(1);
  const [submitState, setSubmitState] = useState<SubmitState>('idle');
  const [submitMessage, setSubmitMessage] = useState('');
  // One key per user intent: reused while retrying, replaced once it succeeds.
  const idempotencyKey = useRef<string | null>(null);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      setLoadState('loading');
      setLoadError('');
      try {
        const [loadedProduct, loadedCart] = await Promise.all([
          api.getProduct(productId, signal),
          api.getCart(signal),
        ]);
        setProduct(loadedProduct);
        setCart(loadedCart);
        setLoadState('ready');
      } catch (error) {
        if (error instanceof DOMException && error.name === 'AbortError') return;
        setLoadError(
          error instanceof ApiError ? error.message : 'Something went wrong while loading the product.',
        );
        setLoadState('error');
      }
    },
    [api, productId],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const sku = useMemo(() => (product ? resolveSku(product, selection) : undefined), [product, selection]);
  const selectionComplete = product
    ? product.options.every((dimension) => selection[dimension.name] !== undefined)
    : false;
  const ceiling = maxQuantity(sku);

  // Availability can shrink under us (someone else took the last unit), so the
  // chosen quantity is re-clamped whenever the resolved SKU changes.
  useEffect(() => {
    setQuantity((current) => clampQuantity(current, sku));
  }, [sku]);

  const handleSelect = useCallback((dimensionName: string, value: string) => {
    idempotencyKey.current = null; // a different variant is a different intent
    setSubmitState('idle');
    setSubmitMessage('');
    setSelection((current) => ({ ...current, [dimensionName]: value }));
  }, []);

  const handleQuantity = useCallback(
    (next: number) => {
      idempotencyKey.current = null;
      setQuantity(clampQuantity(next, sku));
    },
    [sku],
  );

  const handleAddToCart = useCallback(async () => {
    if (!sku || submitState === 'submitting' || sku.available === 0) return;

    const key = idempotencyKey.current ?? createIdempotencyKey();
    idempotencyKey.current = key; // a retry of this intent reuses the same key

    setSubmitState('submitting');
    setSubmitMessage('Adding to cart…');

    let result;
    try {
      result = await api.addToCart(sku.id, quantity, key);
    } catch (error) {
      // The add itself failed: the key is kept so a retry of this intent reuses it.
      setSubmitState('error');
      setSubmitMessage(
        error instanceof ApiError ? error.message : 'Could not add the item. Please try again.',
      );
      return;
    }

    idempotencyKey.current = null; // fulfilled: the next click is a new intent
    setSubmitState('success');
    setSubmitMessage(
      `Added ${result.quantity} × ${product?.name ?? 'item'} (${Object.values(sku.option_values).join(' / ')}).`,
    );

    // The item is already in the cart, so a failure to re-read price and stock must
    // not turn a success into an error: it is a stale-numbers problem, not a failed add.
    try {
      const [freshProduct, freshCart] = await Promise.all([api.getProduct(productId), api.getCart()]);
      setProduct(freshProduct);
      setCart(freshCart);
    } catch {
      // Leave the previous product/cart on screen rather than reporting a false failure.
    }
  }, [api, product?.name, productId, quantity, sku, submitState]);

  if (loadState === 'loading') {
    return (
      <main className="pdp">
        <p className="loading" role="status">
          Loading product…
        </p>
      </main>
    );
  }

  if (loadState === 'error' || !product) {
    return (
      <main className="pdp">
        <div className="error-panel" role="alert">
          <h1>We couldn’t load this product</h1>
          <p>{loadError}</p>
          <button type="button" onClick={() => void load()}>
            Try again
          </button>
        </div>
      </main>
    );
  }

  const soldOut = Boolean(sku) && sku?.available === 0;
  const addDisabled = !sku || soldOut || submitState === 'submitting';
  const buttonLabel =
    submitState === 'submitting'
      ? 'Adding…'
      : !selectionComplete
        ? 'Select options'
        : soldOut
          ? 'Sold out'
          : 'Add to cart';

  const priceCents = sku?.price_cents ?? product.skus[0]?.price_cents ?? 0;

  return (
    <main className="pdp">
      <ProductImage product={product} sku={sku} />

      <section className="details" aria-labelledby="product-name">
        <h1 id="product-name">{product.name}</h1>
        <p className="description">{product.description}</p>

        <p className="price">{formatPrice(priceCents, product.currency)}</p>
        <p className="stock" data-state={soldOut ? 'out' : selectionComplete ? 'in' : 'pending'}>
          {stockLabel(sku, selectionComplete)}
        </p>

        <OptionPicker
          product={product}
          selection={selection}
          disabled={submitState === 'submitting'}
          onSelect={handleSelect}
        />

        <QuantityStepper
          value={quantity}
          max={ceiling}
          disabled={!sku || soldOut}
          onChange={handleQuantity}
        />

        <button className="add-to-cart" type="button" onClick={() => void handleAddToCart()} disabled={addDisabled}>
          {buttonLabel}
        </button>

        <p className="feedback" role="status" aria-live="polite" data-state={submitState}>
          {submitMessage}
        </p>
      </section>

      <CartSummary cart={cart} />
    </main>
  );
}
