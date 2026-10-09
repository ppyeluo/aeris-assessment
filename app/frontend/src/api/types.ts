/** Wire types — kept in sync with the FastAPI schemas. */

export interface OptionDimension {
  name: string;
  values: string[];
}

export interface Sku {
  id: string;
  option_values: Record<string, string>;
  price_cents: number;
  stock: number;
  available: number;
  image: string;
}

export interface Product {
  id: string;
  name: string;
  description: string;
  currency: string;
  image: string;
  options: OptionDimension[];
  skus: Sku[];
}

export interface CartItem {
  sku_id: string;
  product_id: string;
  name: string;
  option_values: Record<string, string>;
  quantity: number;
  price_cents: number;
  line_total_cents: number;
  image: string;
}

export interface Cart {
  items: CartItem[];
  item_count: number;
  total_cents: number;
  currency: string;
}

export interface AddCartItemResponse {
  sku_id: string;
  quantity: number;
  cart_item_count: number;
  cart_total_cents: number;
}

export interface ApiErrorPayload {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}
