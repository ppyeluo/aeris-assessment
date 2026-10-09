import type { Product, Sku } from '../api/types';

interface Props {
  product: Product;
  sku: Sku | undefined;
}

/** Shows the selected variant's image, falling back to the product image. */
export function ProductImage({ product, sku }: Props) {
  const description = sku
    ? Object.entries(sku.option_values)
        .map(([dimension, value]) => `${dimension} ${value}`)
        .join(', ')
    : 'select options to preview';

  return (
    <figure className="gallery">
      <img src={sku?.image ?? product.image} alt={`${product.name} — ${description}`} width={520} height={520} />
    </figure>
  );
}
