"""Estado entre corridas: snapshot en disco y cálculo de novedades."""
from __future__ import annotations

import json
from pathlib import Path

from . import config
from .models import Offer


def load_snapshot(path: Path | None = None) -> dict[str, dict]:
    """Devuelve ``{key: offer_dict}`` de la corrida anterior (o ``{}``)."""
    path = path or config.SNAPSHOT_FILE
    if not path.exists():
        return {}
    try:
        # utf-8-sig tolera un BOM si el archivo se editó a mano en Windows.
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_snapshot(snapshot: dict[str, dict], path: Path | None = None) -> None:
    path = path or config.SNAPSHOT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def merge_snapshot(
    previous: dict[str, dict], current: list[Offer], scraped_stores: set[str]
) -> dict[str, dict]:
    """Reemplaza las entradas de las tiendas scrapeadas y conserva el resto.

    Así, si una tienda falla, su línea base anterior no se pierde.
    """
    merged = {
        k: v for k, v in previous.items() if k.split(":", 1)[0] not in scraped_stores
    }
    for offer in current:
        merged[offer.key] = offer.to_dict()
    return merged


def baseline_stores(
    previous: dict[str, dict], scraped_stores: set[str]
) -> set[str]:
    """Tiendas scrapeadas que aún no tienen ninguna entrada en el snapshot.

    Para ellas esta corrida es su línea base: no se marcan novedades aunque
    otras tiendas ya tuvieran historial.
    """
    known = {k.split(":", 1)[0] for k in previous}
    return {s for s in scraped_stores if s not in known}


def diff_offers(
    current: list[Offer],
    previous: dict[str, dict],
    *,
    scraped_stores: set[str],
) -> tuple[list[Offer], list[tuple[Offer, float]], list[str]]:
    """Calcula (nuevos, bajadas_de_precio, keys_retiradas).

    - nuevos: aparecen ahora y no estaban en el snapshot. Se omiten para las
      tiendas cuya línea base se está creando en esta corrida.
    - bajadas: seguían presentes pero a un precio menor que el guardado.
    - retiradas: estaban en el snapshot para una tienda scrapeada y ya no aparecen.
    """
    nuevos: list[Offer] = []
    bajadas: list[tuple[Offer, float]] = []
    cur_keys = {o.key for o in current}
    baseline = baseline_stores(previous, scraped_stores)

    for offer in current:
        prev = previous.get(offer.key)
        if prev is None:
            if offer.store not in baseline:
                nuevos.append(offer)
            continue
        prev_price = prev.get("price")
        try:
            if prev_price is not None and offer.price < float(prev_price):
                bajadas.append((offer, float(prev_price)))
        except (TypeError, ValueError):
            pass

    retiradas = [
        k
        for k in previous
        if k not in cur_keys and k.split(":", 1)[0] in scraped_stores
    ]
    return nuevos, bajadas, retiradas
