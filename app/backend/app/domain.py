"""Domain model and seed catalogue.

The catalogue is intentionally small but has the shape the exercise asks for:

* one product with two option dimensions (colour and size);
* eight SKUs, including one **unavailable combination** (Black / L has no SKU)
  and one **out-of-stock SKU** (White / S has stock 0).

Prices are integers in minor units (cents) so no money arithmetic is ever done in
floating point.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OptionDimension:
    name: str
    values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Sku:
    id: str
    option_values: dict[str, str]
    price_cents: int
    stock: int
    image: str

    def option_key(self) -> tuple[tuple[str, str], ...]:
        return tuple(sorted(self.option_values.items()))


@dataclass(frozen=True, slots=True)
class Product:
    id: str
    name: str
    description: str
    currency: str
    image: str
    options: tuple[OptionDimension, ...]
    skus: tuple[Sku, ...]

    def by_id(self, sku_id: str) -> Sku | None:
        return next((sku for sku in self.skus if sku.id == sku_id), None)


COLOUR = "Colour"
SIZE = "Size"


def build_seed_product() -> Product:
    """Return a fresh copy of the seed catalogue.

    A function (rather than a module constant) so every test can build an app
    with pristine stock without sharing mutable state.
    """
    skus = (
        Sku("tee-black-s", {COLOUR: "Black", SIZE: "S"}, 3900, 5, "/images/tee-black.svg"),
        Sku("tee-black-m", {COLOUR: "Black", SIZE: "M"}, 3900, 4, "/images/tee-black.svg"),
        # Black / L is deliberately absent -> an impossible combination.
        Sku("tee-white-s", {COLOUR: "White", SIZE: "S"}, 3900, 0, "/images/tee-white.svg"),
        Sku("tee-white-m", {COLOUR: "White", SIZE: "M"}, 3900, 6, "/images/tee-white.svg"),
        Sku("tee-white-l", {COLOUR: "White", SIZE: "L"}, 3900, 3, "/images/tee-white.svg"),
        Sku("tee-sand-s", {COLOUR: "Sand", SIZE: "S"}, 4200, 2, "/images/tee-sand.svg"),
        Sku("tee-sand-m", {COLOUR: "Sand", SIZE: "M"}, 4200, 5, "/images/tee-sand.svg"),
        Sku("tee-sand-l", {COLOUR: "Sand", SIZE: "L"}, 4200, 1, "/images/tee-sand.svg"),
    )
    return Product(
        id="aeris-everyday-tee",
        name="Aeris Everyday Tee",
        description=(
            "A midweight organic cotton tee with a relaxed shoulder. "
            "Pre-shrunk, garment dyed, and made to be worn every day."
        ),
        currency="AUD",
        image="/images/tee-black.svg",
        options=(OptionDimension(COLOUR, ("Black", "White", "Sand")), OptionDimension(SIZE, ("S", "M", "L"))),
        skus=skus,
    )
