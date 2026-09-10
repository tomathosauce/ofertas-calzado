"""Scrapers por tienda."""
from __future__ import annotations

from .base import Store, StoreError
from .converse import ConverseStore
from .vans import VansStore

STORE_CLASSES: dict[str, type[Store]] = {
    "converse": ConverseStore,
    "vans": VansStore,
}

__all__ = ["Store", "StoreError", "ConverseStore", "VansStore", "STORE_CLASSES"]
