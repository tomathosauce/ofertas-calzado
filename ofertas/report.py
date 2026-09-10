"""Generación del reporte HTML y del histórico CSV."""
from __future__ import annotations

import csv
import datetime as dt
import re
import shutil

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import config
from .models import Offer

_HISTORY_FIELDS = [
    "run_ts", "store", "product_id", "name", "category", "gender", "age_group",
    "url", "price", "old_price", "discount_pct", "status",
]


def _size_sort_key(size: str) -> tuple[float, str]:
    """Orden 'natural': primero por el número que aparezca, luego alfabético."""
    match = re.search(r"\d+(?:\.\d+)?", size)
    return (float(match.group()) if match else 999.0, size.lower())


def _sizes_by_store(offers: list[Offer]) -> dict[str, list[str]]:
    buckets: dict[str, set[str]] = {}
    for offer in offers:
        for size in offer.sizes_available:
            buckets.setdefault(offer.store, set()).add(size)
    return {
        store: sorted(values, key=_size_sort_key)
        for store, values in sorted(buckets.items())
    }


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(config.TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def write_report(
    *,
    offers: list[Offer],
    nuevos: list[Offer],
    bajadas: list[tuple[Offer, float]],
    retiradas: list[str],
    errors: list[str],
    run_ts: dt.datetime,
):
    """Escribe ``ofertas_<timestamp>.html`` y actualiza ``ofertas_latest.html``."""
    config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    by_store: dict[str, int] = {}
    for offer in offers:
        by_store[offer.store] = by_store.get(offer.store, 0) + 1

    ordered = sorted(offers, key=lambda o: o.discount_pct, reverse=True)
    context = {
        "run_ts_iso": run_ts.isoformat(timespec="seconds"),
        "run_ts_human": run_ts.strftime("%d/%m/%Y %H:%M"),
        "offers": ordered,
        "nuevos": sorted(nuevos, key=lambda o: o.discount_pct, reverse=True),
        "bajadas": sorted(bajadas, key=lambda t: t[1] - t[0].price, reverse=True),
        "retiradas": retiradas,
        "errors": errors,
        "counts": by_store,
        "total": len(offers),
        "sizes_by_store": _sizes_by_store(ordered),
        "genders_present": sorted({o.gender for o in ordered if o.gender}),
        "ages_present": sorted({o.age_group for o in ordered if o.age_group}),
    }

    html = _environment().get_template("report.html.j2").render(**context)
    out_path = config.REPORTS_DIR / f"ofertas_{run_ts.strftime('%Y-%m-%d_%H%M')}.html"
    out_path.write_text(html, encoding="utf-8")
    shutil.copyfile(out_path, config.LATEST_REPORT)
    return out_path


def _rotate_history_if_schema_changed() -> None:
    """Si el CSV existente tiene otras columnas, lo archiva y empieza uno nuevo."""
    path = config.HISTORY_CSV
    if not path.exists():
        return
    try:
        with path.open("r", encoding="utf-8", newline="") as fh:
            header = next(csv.reader(fh), [])
    except OSError:
        return
    if header and header != _HISTORY_FIELDS:
        backup = path.with_name("history_legacy.csv")
        if backup.exists():
            backup = path.with_name(f"history_legacy_{dt.datetime.now():%Y%m%d%H%M%S}.csv")
        path.rename(backup)


def append_history(
    *,
    offers: list[Offer],
    nuevos: list[Offer],
    bajadas: list[tuple[Offer, float]],
    run_ts: dt.datetime,
) -> None:
    """Añade una fila por oferta al CSV histórico (crea cabecera si no existe)."""
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    nuevos_keys = {o.key for o in nuevos}
    bajada_keys = {o.key for o, _ in bajadas}

    _rotate_history_if_schema_changed()
    is_new = not config.HISTORY_CSV.exists()
    with config.HISTORY_CSV.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_HISTORY_FIELDS)
        if is_new:
            writer.writeheader()
        for offer in offers:
            if offer.key in nuevos_keys:
                status = "nuevo"
            elif offer.key in bajada_keys:
                status = "price_drop"
            else:
                status = "existente"
            writer.writerow({
                "run_ts": run_ts.isoformat(timespec="seconds"),
                "store": offer.store,
                "product_id": offer.product_id,
                "name": offer.name,
                "category": offer.category,
                "gender": offer.gender,
                "age_group": offer.age_group,
                "url": offer.url,
                "price": f"{offer.price:.2f}",
                "old_price": f"{offer.old_price:.2f}" if offer.old_price else "",
                "discount_pct": offer.discount_pct,
                "status": status,
            })
