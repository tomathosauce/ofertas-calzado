#!/usr/bin/env python3
"""Monitor manual de ofertas de calzado: Converse Panamá + Vans Panamá.

Uso típico:

    python scrape_ofertas.py            # ambas tiendas -> reporte + CSV + resumen
    python scrape_ofertas.py --store vans --open
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

# La consola de Windows suele venir en cp1252; forzamos UTF-8 para los acentos.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

from ofertas import config, report, state
from ofertas.models import Offer
from ofertas.stores import STORE_CLASSES, StoreError


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scrape_ofertas",
        description="Monitorea ofertas de calzado en Converse PA y Vans PA.",
    )
    parser.add_argument(
        "--store",
        choices=sorted(STORE_CLASSES),
        action="append",
        metavar="TIENDA",
        help="limita a una tienda (se puede repetir); por defecto, todas",
    )
    parser.add_argument(
        "--open", action="store_true", help="abre el reporte HTML al terminar"
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="no genera HTML/CSV; solo actualiza el estado y muestra el resumen",
    )
    parser.add_argument(
        "--all-products",
        action="store_true",
        help="ignora el filtro de calzado (incluye ropa y accesorios)",
    )
    parser.add_argument(
        "--no-details",
        action="store_true",
        help="no visita las fichas de Converse para leer tallas (más rápido; "
        "usa solo la caché existente)",
    )
    return parser.parse_args(argv)


def _scrape_store(name: str):
    store = STORE_CLASSES[name]()
    offers = store.fetch_offers()
    kept = [
        o
        for o in offers
        if o.is_offer and o.discount_pct >= config.MIN_DISCOUNT_PCT
    ]
    return kept, store


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.all_products:
        config.FOOTWEAR_ONLY = False
    if args.no_details:
        config.CONVERSE_FETCH_DETAILS = False

    stores = args.store or list(config.STORES)
    run_ts = dt.datetime.now()

    previous = state.load_snapshot()

    all_offers: list[Offer] = []
    scraped_stores: set[str] = set()
    errors: list[str] = []

    kind = "calzado" if config.FOOTWEAR_ONLY else "producto"
    for name in stores:
        print(f"[{name}] descargando ofertas…", flush=True)
        try:
            offers, store = _scrape_store(name)
        except StoreError as err:
            errors.append(f"{name}: {err}")
            print(f"[{name}] ERROR: {err}", file=sys.stderr)
            continue
        if store.detail_warning:
            errors.append(store.detail_warning)
            print(f"[{name}] AVISO: {store.detail_warning}", file=sys.stderr)
        if not offers:
            # Muy improbable en estas tiendas: lo tratamos como fallo y
            # conservamos la línea base anterior en vez de borrarla.
            msg = "no se encontraron ofertas (posible cambio en la web)"
            errors.append(f"{name}: {msg}")
            print(f"[{name}] AVISO: {msg}", file=sys.stderr)
            continue
        all_offers.extend(offers)
        scraped_stores.add(name)
        print(f"[{name}] {len(offers)} ofertas de {kind}")

    if not scraped_stores:
        print("\nNo se pudo obtener ninguna tienda.", file=sys.stderr)
        return 1

    nuevos, bajadas, retiradas = state.diff_offers(
        all_offers, previous, scraped_stores=scraped_stores
    )
    baseline = state.baseline_stores(previous, scraped_stores)

    print()
    if baseline:
        print(
            "Línea base para: "
            + ", ".join(sorted(baseline))
            + " (sin marcar novedades en esta corrida)."
        )
    for name in sorted(scraped_stores):
        total = sum(1 for o in all_offers if o.store == name)
        nuevas = sum(1 for o in nuevos if o.store == name)
        print(f"  {name:9} {total:3} en oferta · {nuevas:3} nuevas")
    if bajadas:
        print(f"  bajadas de precio: {len(bajadas)}")
    if errors:
        print(f"  tiendas con error: {len(errors)}")

    if not args.no_report:
        out_path = report.write_report(
            offers=all_offers,
            nuevos=nuevos,
            bajadas=bajadas,
            retiradas=retiradas,
            errors=errors,
            run_ts=run_ts,
        )
        report.append_history(
            offers=all_offers, nuevos=nuevos, bajadas=bajadas, run_ts=run_ts
        )
        print(f"\nReporte:   {out_path}")
        print(f"Más reciente: {config.LATEST_REPORT}")
        print(f"Histórico: {config.HISTORY_CSV}")
        if args.open and hasattr(os, "startfile"):
            os.startfile(out_path)  # type: ignore[attr-defined]  # noqa: S606

    merged = state.merge_snapshot(previous, all_offers, scraped_stores)
    state.save_snapshot(merged)

    # Código de salida 2 si alguna tienda falló pero otra funcionó (para scripts).
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
