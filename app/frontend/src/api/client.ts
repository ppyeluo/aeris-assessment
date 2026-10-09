/**
 * Thin HTTP layer.
 *
 * A transport failure or a non-2xx response is normalised into an ``ApiError``,
 * so the UI has exactly one error shape to render.  The server's error envelope
 * (``{"error": {...}}``) is unwrapped here; components never see raw response
 * objects.  A 2xx body is returned as-is and is expected to be JSON.
 */

import type { AddCartItemResponse, ApiErrorPayload, Cart, Product } from './types';

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details?: Record<string, unknown>) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, init);
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new ApiError(0, 'network_error', 'Could not reach the server. Please try again.');
  }

  const contentType = response.headers.get('content-type') ?? '';
  const payload: unknown = contentType.includes('application/json') ? await response.json() : undefined;

  if (!response.ok) {
    const body = payload as ApiErrorPayload | undefined;
    throw new ApiError(
      response.status,
      body?.error?.code ?? 'unknown_error',
      body?.error?.message ?? `Request failed with status ${response.status}`,
      body?.error?.details,
    );
  }
  return payload as T;
}

export function getProduct(productId: string, signal?: AbortSignal): Promise<Product> {
  return request<Product>(`/api/products/${encodeURIComponent(productId)}`, { signal });
}

export function getCart(signal?: AbortSignal): Promise<Cart> {
  return request<Cart>('/api/cart', { signal });
}

export function addToCart(
  skuId: string,
  quantity: number,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<AddCartItemResponse> {
  return request<AddCartItemResponse>('/api/cart/items', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': idempotencyKey,
    },
    body: JSON.stringify({ sku_id: skuId, quantity }),
    signal,
  });
}
