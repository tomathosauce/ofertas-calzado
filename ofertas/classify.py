"""Clasificación de un producto en (género, edad) a partir de texto suelto.

Entrada: los términos que ya trae cada tienda —el badge de Converse
("Preescolar Zapatillas Corte Bajo") o los tags de Vans (["NINOS", "Unisex", …])—.
Salida: género plegado a 3 grupos y grupo de edad.
"""
from __future__ import annotations

import unicodedata
from collections.abc import Iterable

# Palabras (ya normalizadas) que marcan calzado infantil.
_KID_WORDS = {
    "infante", "infantes", "infantil", "preescolar", "joven", "juvenil",
    "nino", "ninos", "nina", "ninas", "nino/nina", "toddler", "bebe",
    "kids", "kid", "td", "ps", "gs", "cribster",
}
_WOMAN_WORDS = {"mujer", "mujeres", "women", "woman", "nina", "ninas", "girls"}
_MAN_WORDS = {"hombre", "hombres", "men", "man", "nino", "ninos", "boys"}

GENDERS = ("mujer", "hombre", "unisex")
AGES = ("adulto", "nino")


def _sin_acentos(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalizar(terminos: Iterable[str]) -> set[str]:
    out: set[str] = set()
    for termino in terminos:
        limpio = _sin_acentos(str(termino)).strip().lower()
        if limpio:
            out.add(limpio)
    return out


def clasificar(terminos: Iterable[str]) -> tuple[str, str]:
    """Devuelve ``(genero, edad)`` con ``genero`` en :data:`GENDERS` y
    ``edad`` en :data:`AGES`. Todo lo que no sea claramente mujer/hombre
    queda como ``"unisex"``."""
    palabras = _normalizar(terminos)

    edad = "nino" if palabras & _KID_WORDS else "adulto"

    if palabras & _WOMAN_WORDS:
        genero = "mujer"
    elif palabras & _MAN_WORDS:
        genero = "hombre"
    else:
        genero = "unisex"

    return genero, edad
