"""Modelo de datos común a todas las tiendas."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone


@dataclass
class Offer:
    """Una oferta de un producto en una tienda concreta."""

    store: str                       # "converse" | "vans"
    product_id: str                  # id estable dentro de la tienda
    name: str
    url: str
    price: float
    old_price: float | None = None
    category: str = ""               # texto de categoría/tipo tal cual lo da la tienda
    gender: str = ""                 # "mujer" | "hombre" | "unisex"
    age_group: str = ""              # "adulto" | "nino"
    image_url: str = ""
    currency: str = "USD"
    sizes_available: list[str] = field(default_factory=list)
    scraped_at: str = ""

    def __post_init__(self) -> None:
        if not self.scraped_at:
            self.scraped_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    @property
    def key(self) -> str:
        """Clave única entre tiendas: ``store:product_id``."""
        return f"{self.store}:{self.product_id}"

    @property
    def discount_pct(self) -> int:
        if self.old_price and self.old_price > 0 and self.price < self.old_price:
            return round((1 - self.price / self.old_price) * 100)
        return 0

    @property
    def is_offer(self) -> bool:
        """False solo si hay precio anterior y NO es menor que el actual."""
        return not (self.old_price is not None and self.old_price <= self.price)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["discount_pct"] = self.discount_pct
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Offer":
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in allowed})
