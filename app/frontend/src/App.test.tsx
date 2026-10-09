import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import App, { type PdpApi } from './App';
import { ApiError } from './api/client';
import type { AddCartItemResponse, Cart, Product } from './api/types';

/**
 * Fixture deliberately contains both awkward shapes:
 *   - Black / L exists but has no stock  -> "Sold out"
 *   - White / M and White / L have no SKU -> "Unavailable"
 */
const product: Product = {
  id: 'tee',
  name: 'Aeris Everyday Tee',
  description: 'A midweight organic cotton tee.',
  currency: 'AUD',
  image: '/images/tee-black.svg',
  options: [
    { name: 'Colour', values: ['Black', 'White'] },
    { name: 'Size', values: ['S', 'M', 'L'] },
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
      stock: 5,
      available: 5,
      image: '/images/tee-black.svg',
    },
    {
      id: 'black-l',
      option_values: { Colour: 'Black', Size: 'L' },
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

const emptyCart: Cart = { items: [], item_count: 0, total_cents: 0, currency: 'AUD' };

function makeApi(overrides: Partial<PdpApi> = {}): PdpApi {
  const api = {
    getProduct: vi.fn(async () => product),
    getCart: vi.fn(async () => emptyCart),
    addToCart: vi.fn(
      async (skuId: string, quantity: number): Promise<AddCartItemResponse> => ({
        sku_id: skuId,
        quantity,
        cart_item_count: quantity,
        cart_total_cents: 3900 * quantity,
      }),
    ),
    ...overrides,
  };
  return api as unknown as PdpApi;
}

async function renderReady(api: PdpApi): Promise<PdpApi> {
  render(<App productId={product.id} api={api} />);
  await screen.findByRole('heading', { name: product.name });
  return api;
}

async function choose(user: ReturnType<typeof userEvent.setup>, colour: string, size: string) {
  await user.click(screen.getByRole('radio', { name: colour }));
  await user.click(screen.getByRole('radio', { name: size }));
}

describe('Variant PDP', () => {
  it('renders the product and asks for options before enabling add-to-cart', async () => {
    await renderReady(makeApi());

    expect(screen.getByText('$39.00')).toBeInTheDocument();
    expect(screen.getByText(/select a colour and size/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /select options/i })).toBeDisabled();
  });

  it('disables a sold-out combination and explains why', async () => {
    await renderReady(makeApi());

    const sizeL = screen.getByRole('radio', { name: 'L' });
    expect(sizeL).toBeDisabled();
    expect(sizeL).toHaveAccessibleDescription('Sold out');
  });

  it('disables a combination that has no SKU once the other dimension is chosen', async () => {
    const user = userEvent.setup();
    await renderReady(makeApi());

    // White / M does not exist, so choosing White must make M impossible.
    await user.click(screen.getByRole('radio', { name: 'White' }));

    const sizeM = screen.getByRole('radio', { name: 'M' });
    expect(sizeM).toBeDisabled();
    expect(sizeM).toHaveAccessibleDescription('Unavailable');
  });

  it('resolves the SKU, updates price and stock, and adds the right variant', async () => {
    const user = userEvent.setup();
    const api = await renderReady(makeApi());

    await choose(user, 'White', 'S');

    expect(screen.getByText('$42.00')).toBeInTheDocument();
    expect(screen.getByText(/only 1 left/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /add to cart/i }));

    await waitFor(() => expect(api.addToCart).toHaveBeenCalledTimes(1));
    expect(api.addToCart).toHaveBeenCalledWith('white-s', 1, expect.any(String));
    expect(await screen.findByText(/added 1/i)).toBeInTheDocument();
  });

  it('submits only once while a request is in flight', async () => {
    const user = userEvent.setup();
    let release: (value: AddCartItemResponse) => void = () => {};
    const addToCart = vi.fn(
      () =>
        new Promise<AddCartItemResponse>((resolve) => {
          release = resolve;
        }),
    );
    await renderReady(makeApi({ addToCart }));
    await choose(user, 'Black', 'S');

    await user.click(screen.getByRole('button', { name: /add to cart/i }));

    const pendingButton = screen.getByRole('button', { name: /adding/i });
    expect(pendingButton).toBeDisabled();

    // A second click (and a raw DOM click) must not queue another request.
    fireEvent.click(pendingButton);
    expect(addToCart).toHaveBeenCalledTimes(1);

    release({ sku_id: 'black-s', quantity: 1, cart_item_count: 1, cart_total_cents: 3900 });
    expect(await screen.findByText(/added 1/i)).toBeInTheDocument();
  });

  it('surfaces a structured server error', async () => {
    const user = userEvent.setup();
    const addToCart = vi.fn(async () => {
      throw new ApiError(409, 'insufficient_stock', 'Only 0 unit(s) of tee-black-s are available');
    });
    await renderReady(makeApi({ addToCart }));
    await choose(user, 'Black', 'S');

    await user.click(screen.getByRole('button', { name: /add to cart/i }));

    expect(await screen.findByText(/only 0 unit/i)).toBeInTheDocument();
  });

  it('clamps quantity to the available stock', async () => {
    const user = userEvent.setup();
    await renderReady(makeApi());
    await choose(user, 'White', 'S'); // only 1 available

    const input = screen.getByRole('spinbutton', { name: /quantity/i });
    expect(input).toHaveValue(1);
    expect(screen.getByRole('button', { name: /increase quantity/i })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: /decrease quantity/i }));
    expect(input).toHaveValue(1);
  });

  it('keeps the success state when the post-add refresh fails', async () => {
    const user = userEvent.setup();
    const getProduct = vi
      .fn()
      .mockResolvedValueOnce(product) // initial load
      .mockRejectedValueOnce(new ApiError(0, 'network_error', 'Could not reach the server.'));
    await renderReady(makeApi({ getProduct }));
    await choose(user, 'Black', 'S');

    await user.click(screen.getByRole('button', { name: /add to cart/i }));

    // The add succeeded, so the refresh failure must not be reported as a failed add.
    expect(await screen.findByText(/added 1/i)).toBeInTheDocument();
    expect(screen.queryByText(/could not reach the server/i)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /add to cart/i })).toBeEnabled();
  });

  it('offers a retry when the product fails to load', async () => {
    const user = userEvent.setup();
    const getProduct = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(0, 'network_error', 'Could not reach the server. Please try again.'))
      .mockResolvedValueOnce(product);

    render(<App productId={product.id} api={makeApi({ getProduct })} />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/couldn’t load this product/i);

    await user.click(screen.getByRole('button', { name: /try again/i }));

    expect(await screen.findByRole('heading', { name: product.name })).toBeInTheDocument();
  });
});
