"""Vans Panamá — tienda Shopify.

Shopify expone el catálogo de una colección en JSON abierto:
``/collections/<handle>/products.json?limit=250&page=N``
así que no hace falta navegador ni parsear HTML.
"""
from __future__ import annotations

import time

import httpx

from .. import config
from ..classify import clasificar
from ..models import Offer
from .base import Store, StoreError


class VansStore(Store):
    name = "vans"

    def fetch_offers(self) -> list[Offer]:
        offers: list[Offer] = []
        for product in self._download_all():
            if config.FOOTWEAR_ONLY and not _is_footwear(product):
                continue
            offer = _to_offer(product)
            if offer is not None:
                offers.append(offer)
        return offers

    # ------------------------------------------------------------------
    def _download_all(self) -> list[dict]:
        headers = {"User-Agent": config.USER_AGENT, "Accept": "application/json"}
        last_err: Exception | None = None
        for attempt in range(config.RETRIES + 1):
            try:
                products: list[dict] = []
                with httpx.Client(
                    timeout=config.HTTP_TIMEOUT,
                    headers=headers,
                    follow_redirects=True,
                ) as client:
                    for page in range(1, config.MAX_PAGES + 1):
                        resp = client.get(
                            config.VANS_PRODUCTS_JSON,
                            params={"limit": 250, "page": page},
                        )
                        resp.raise_for_status()
                        batch = resp.json().get("products", [])
                        if not batch:
                            break
                        products.extend(batch)
                        time.sleep(config.REQUEST_DELAY[0])
                if not products:
                    # Shopify devuelve 200 y {"products":[]} si cambia el handle
                    # de la colección: lo tratamos como fallo, no como "sin ofertas".
                    raise StoreError(
                        "Vans no devolvió productos; ¿cambió la colección "
                        f"'{config.VANS_PRODUCTS_JSON}'?"
                    )
                return products
            except (httpx.HTTPError, ValueError) as err:  # ValueError = JSON inválido
                last_err = err
                time.sleep(2 * (attempt + 1))
        raise StoreError(f"no se pudo descargar el catálogo de Vans: {last_err}")


def _is_footwear(product: dict) -> bool:
    ptype = (product.get("product_type") or "").upper()
    tags = {t.upper() for t in product.get("tags", [])}
    return ptype == config.VANS_FOOTWEAR_TYPE or config.VANS_FOOTWEAR_TYPE in tags


def _to_offer(product: dict) -> Offer | None:
    priced: list[tuple[float, float | None, dict]] = []
    for variant in product.get("variants", []):
        try:
            price = float(variant["price"])
        except (KeyError, TypeError, ValueError):
            continue
        raw_cap = variant.get("compare_at_price")
        cap = float(raw_cap) if raw_cap not in (None, "") else None
        priced.append((price, cap, variant))

    if not priced:
        return None

    price, _, _ = min(priced, key=lambda t: t[0])
    caps = [cap for _, cap, _ in priced if cap]
    old_price = max(caps) if caps else None
    if not old_price or old_price <= price:
        return None  # no es una oferta real

    # La talla es la 1ª opción de la variante ("Talla"); solo las disponibles.
    sizes: list[str] = []
    for _, _, variant in priced:
        if not variant.get("available"):
            continue
        talla = str(variant.get("option1") or variant.get("title") or "").strip()
        if talla and talla not in sizes:
            sizes.append(talla)

    images = product.get("images", [])
    image_url = ""
    if images:
        first = images[0]
        image_url = first.get("src", "") if isinstance(first, dict) else str(first)

    gender, age_group = clasificar(product.get("tags", []))

    return Offer(
        store="vans",
        product_id=str(product.get("id")),
        name=(product.get("title") or "").strip(),
        url=config.VANS_PRODUCT_URL.format(handle=product.get("handle", "")),
        price=price,
        old_price=old_price,
        category=(product.get("product_type") or "").title(),
        gender=gender,
        age_group=age_group,
        image_url=image_url,
        sizes_available=sizes,
    )
