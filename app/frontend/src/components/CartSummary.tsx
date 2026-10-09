import type { Cart } from '../api/types';
import { formatPrice } from '../domain/variants';

interface Props {
  cart: Cart | null;
}

/** Read-only cart summary; the page refreshes it after every add. */
export function CartSummary({ cart }: Props) {
  const itemCount = cart?.item_count ?? 0;

  return (
    <aside className="cart" aria-label="Cart">
      <h2>Your cart</h2>
      {!cart || itemCount === 0 ? (
        <p className="cart-empty">Your cart is empty.</p>
      ) : (
        <>
          <ul className="cart-items">
            {cart.items.map((item) => (
              <li key={item.sku_id}>
                <span className="cart-item-name">
                  {item.name} · {Object.values(item.option_values).join(' / ')}
                </span>
                <span className="cart-item-qty">×{item.quantity}</span>
                <span className="cart-item-total">
                  {formatPrice(item.line_total_cents, cart.currency)}
                </span>
              </li>
            ))}
          </ul>
          <p className="cart-total">
            <span>
              {itemCount} item{itemCount === 1 ? '' : 's'}
            </span>
            <strong>{formatPrice(cart.total_cents, cart.currency)}</strong>
          </p>
        </>
      )}
    </aside>
  );
}
