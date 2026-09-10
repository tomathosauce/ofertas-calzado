"""Interfaz común de las tiendas."""
from __future__ import annotations

import abc

from ..models import Offer


class StoreError(RuntimeError):
    """No se pudieron obtener las ofertas de una tienda."""


class Store(abc.ABC):
    name: str
    # Aviso no fatal que el reporte puede mostrar (p. ej. tallas no encontradas).
    detail_warning: str | None = None

    @abc.abstractmethod
    def fetch_offers(self) -> list[Offer]:
        """Devuelve la lista de ofertas actuales (ya filtradas por calzado
        si ``config.FOOTWEAR_ONLY`` está activo). Lanza :class:`StoreError`
        si la descarga falla por completo."""
        raise NotImplementedError
