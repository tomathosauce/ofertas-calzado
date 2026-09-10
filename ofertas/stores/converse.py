"""Converse Panamá — tienda Magento 2 tras protección Imperva/Incapsula.

Estrategia de descarga (:class:`_Fetcher`), compartida por el listado y las fichas:
1. Intentar un GET simple con ``httpx`` y cabeceras de navegador.
2. En cuanto Imperva responde con su reto (o 403), abrir **un solo** Chromium con
   Playwright, resolver el reto una vez y reutilizar ese contexto para todo lo
   demás. Las fichas se piden con ``fetch()`` dentro de la página ya autorizada
   (mucho más rápido que navegar a cada una).

Tanto el listado como el bloque de tallas de la ficha están en el HTML servido
por el servidor, así que basta con parsear HTML (no hace falta esperar a la
hidratación con JS).
"""
from __future__ import annotations

import json
import random
import re
import time
import warnings
from collections.abc import Iterator, Sequence
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

try:  # bs4 avisa si por error le pasan algo que parece una URL en vez de HTML
    from bs4 import MarkupResemblesLocatorWarning

    warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)
except ImportError:  # versiones antiguas de bs4
    pass

from .. import config
from ..classify import clasificar
from ..models import Offer
from .base import Store, StoreError

_IMPERVA_MARKERS = (
    "_Incapsula_Resource",
    "Incapsula incident",
    "Additional security check is required",
    "Request unsuccessful. Incapsula",
)
_PRODUCT_SELECTOR = "li.product-item, li.item.product.product-item"

_HTTP_HEADERS = {
    "User-Agent": config.BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-PA,es;q=0.9,en;q=0.8",
}

# fetch() serie dentro de la página ya autorizada por Imperva.
_FETCH_MANY_JS = """
async (urls) => {
  const out = [];
  for (const u of urls) {
    try {
      const r = await fetch(u, { credentials: 'include' });
      out.push(r.ok ? await r.text() : null);
    } catch (e) { out.push(null); }
  }
  return out;
}
"""


class ConverseStore(Store):
    name = "converse"

    def fetch_offers(self) -> list[Offer]:
        self.detail_warning = None
        with _Fetcher() as fetch:
            offers = self._collect_offers(fetch)
            if config.CONVERSE_FETCH_DETAILS:
                self._add_sizes(offers, fetch)
            else:
                self._fill_sizes_from_cache(offers)
        return offers

    # -- listado ----------------------------------------------------------
    def _collect_offers(self, fetch: "_Fetcher") -> list[Offer]:
        first = fetch.html(_page_url(1), expect_products=True)
        htmls = [first]
        for num in range(2, _page_count(first) + 1):
            htmls.append(fetch.html(_page_url(num), expect_products=True))

        offers: list[Offer] = []
        seen: set[str] = set()
        for html in htmls:
            for offer in _parse_page(html):
                if offer.key in seen:
                    continue
                if config.FOOTWEAR_ONLY and not re.search(
                    config.FOOTWEAR_CATEGORY_RE, offer.category, re.IGNORECASE
                ):
                    continue
                seen.add(offer.key)
                offers.append(offer)
        if not offers:
            raise StoreError("no se obtuvo ningún producto de Converse")
        return offers

    # -- tallas por ficha ----------------------------------------------------
    def _add_sizes(self, offers: list[Offer], fetch: "_Fetcher") -> None:
        cache = _load_cache()
        now = datetime.now(timezone.utc)

        pending = [o for o in offers if _is_stale(cache.get(o.product_id), now)]
        pending = pending[: config.CONVERSE_PDP_MAX]

        htmls = fetch.html_many([o.url for o in pending])
        empty_hits = 0
        for offer in pending:
            html = htmls.get(offer.url)
            sizes = _parse_sizes(html) if html else []
            if not sizes:
                empty_hits += 1
            cache[offer.product_id] = {
                "sizes": sizes,
                "url": offer.url,
                "fetched_at": now.isoformat(timespec="seconds"),
            }

        self._fill_sizes_from_cache(offers, cache)

        # Podar fichas que ya no están en oferta y guardar.
        vigentes = {o.product_id for o in offers}
        for pid in list(cache):
            if pid not in vigentes:
                del cache[pid]
        _save_cache(cache)

        if pending and empty_hits >= max(3, int(0.8 * len(pending))):
            self.detail_warning = (
                f"converse: {empty_hits}/{len(pending)} fichas no devolvieron "
                "tallas (¿cambió el HTML de la PDP?)"
            )

    @staticmethod
    def _fill_sizes_from_cache(offers: list[Offer], cache: dict | None = None) -> None:
        cache = cache if cache is not None else _load_cache()
        for offer in offers:
            entry = cache.get(offer.product_id)
            if entry and entry.get("sizes"):
                offer.sizes_available = list(entry["sizes"])


# --- descarga: httpx con caída a un único Chromium persistente --------------
def _httpx_get(url: str) -> str | None:
    try:
        with httpx.Client(
            timeout=config.HTTP_TIMEOUT, headers=_HTTP_HEADERS, follow_redirects=True
        ) as client:
            resp = client.get(url)
    except httpx.HTTPError:
        return None
    return resp.text if resp.status_code == 200 else None


def _blocked(html: str | None) -> bool:
    return bool(html) and any(m in html for m in _IMPERVA_MARKERS)


def _chunks(seq: Sequence, size: int) -> Iterator[list]:
    for i in range(0, len(seq), size):
        yield list(seq[i : i + size])


class _Fetcher:
    """Sesión de descarga para Converse. Usa httpx mientras funcione; en cuanto
    Imperva bloquea, abre un Chromium, pasa el reto una vez y lo reutiliza."""

    def __init__(self) -> None:
        self._pw = None
        self._browser = None
        self._page = None
        self._httpx_ok = True

    def __enter__(self) -> "_Fetcher":
        return self

    def __exit__(self, *_exc) -> None:
        for closer in (
            getattr(self._browser, "close", None),
            getattr(self._pw, "stop", None),
        ):
            if closer:
                try:
                    closer()
                except Exception:  # noqa: BLE001
                    pass

    # -- una URL -------------------------------------------------------------
    def html(self, url: str, *, expect_products: bool = False) -> str:
        if self._page is None and self._httpx_ok:
            body = _httpx_get(url)
            if body and not _blocked(body) and (
                not expect_products or "product-item" in body
            ):
                time.sleep(random.uniform(*config.REQUEST_DELAY))
                return body
            self._httpx_ok = False  # a partir de aquí, todo por navegador

        self._ensure_browser()
        if _norm(url) != _norm(self._page.url):
            self._navigate(url, expect_products=expect_products)
        time.sleep(random.uniform(*config.REQUEST_DELAY))
        return self._page.content()

    # -- muchas URLs -> {url: html|None} -----------------------------------
    def html_many(self, urls: list[str]) -> dict[str, str | None]:
        out: dict[str, str | None] = {}
        if not urls:
            return out

        if self._page is None and self._httpx_ok:
            for url in urls:
                body = _httpx_get(url)
                if not body or _blocked(body):
                    self._httpx_ok = False
                    break
                out[url] = body
                time.sleep(random.uniform(*config.REQUEST_DELAY))
            if self._httpx_ok:
                return out

        remaining = [u for u in urls if u not in out]
        if remaining:
            self._ensure_browser()
            for chunk in _chunks(remaining, 8):
                try:
                    got = self._page.evaluate(_FETCH_MANY_JS, chunk)
                except Exception:  # noqa: BLE001
                    got = [None] * len(chunk)
                for url, html in zip(chunk, got):
                    out[url] = html or None
                time.sleep(random.uniform(*config.REQUEST_DELAY))
        return out

    # -- navegador --------------------------------------------------------
    def _ensure_browser(self) -> None:
        if self._page is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as err:
            raise StoreError(
                "falta Playwright para saltar la protección de Converse. "
                "Instala con:  pip install playwright  &&  playwright install chromium"
            ) from err
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        context = self._browser.new_context(
            user_agent=config.BROWSER_UA,
            locale="es-PA",
            viewport={"width": 1366, "height": 900},
        )
        self._page = context.new_page()
        # Primera carga: resolver el reto de Imperva una sola vez.
        self._navigate(config.CONVERSE_SALE_URL, expect_products=True)

    def _navigate(self, url: str, *, expect_products: bool = False) -> None:
        page = self._page
        for _attempt in range(2):
            page.goto(url, wait_until="domcontentloaded", timeout=45_000)
            for _ in range(8):
                if not _blocked(_safe_content(page)):
                    break
                page.wait_for_timeout(3_000)
            if not _blocked(_safe_content(page)):
                break
        else:
            raise StoreError(
                "Converse muestra un reto de seguridad (Imperva) que no se resolvió "
                "solo. Ejecuta una vez con navegador visible (headless=False) para "
                "pasar la verificación."
            )
        if expect_products:
            try:
                page.wait_for_selector(_PRODUCT_SELECTOR, timeout=20_000)
            except Exception as err:  # noqa: BLE001
                raise StoreError(f"no aparecieron productos en {url}: {err}") from err


def _safe_content(page) -> str:
    try:
        return page.content()
    except Exception:  # noqa: BLE001
        return ""


def _norm(url: str) -> str:
    return (url or "").split("#")[0].rstrip("/")


def _page_url(page: int) -> str:
    if page <= 1:
        return config.CONVERSE_SALE_URL
    return f"{config.CONVERSE_SALE_URL}?p={page}"


def _page_count(html: str) -> int:
    soup = BeautifulSoup(html, "lxml")
    nums = {1}
    for anchor in soup.select(".pages a"):
        match = re.search(r"[?&]p=(\d+)", anchor.get("href", ""))
        if match:
            nums.add(int(match.group(1)))
        text = anchor.get_text(strip=True)
        if text.isdigit():
            nums.add(int(text))
    return min(max(nums), config.MAX_PAGES)


# --- parseo del listado -------------------------------------------------------
def _parse_page(html: str) -> Iterator[Offer]:
    soup = BeautifulSoup(html, "lxml")
    for li in soup.select(_PRODUCT_SELECTOR):
        offer = _parse_item(li)
        if offer is not None:
            yield offer


def _parse_item(li) -> Offer | None:
    link = li.select_one("a.product-item-link")
    if link is None:
        return None
    url = link.get("href", "").strip()
    name = link.get_text(strip=True)

    info = li.select_one('[id^="product-item-info_"]')
    product_id = ""
    if info is not None and info.get("id"):
        product_id = info["id"].rsplit("_", 1)[-1]
    if not product_id:
        match = re.search(r"-(\d+)\.html", url)
        product_id = match.group(1) if match else url

    price = _price(li.select_one('[data-price-type="finalPrice"]'))
    if price is None:
        return None
    old_price = _price(li.select_one('[data-price-type="oldPrice"]'))

    img = li.select_one("img.product-image-photo")
    image_url = ""
    if img is not None:
        image_url = (img.get("src") or img.get("data-src") or "").strip()

    badge = li.select_one(".product-item__secondary-badge")
    category = badge.get_text(" ", strip=True) if badge is not None else ""
    gender, age_group = clasificar(category.split())

    return Offer(
        store="converse",
        product_id=str(product_id),
        name=name,
        url=url,
        price=price,
        old_price=old_price,
        category=category,
        gender=gender,
        age_group=age_group,
        image_url=image_url,
    )


def _price(el) -> float | None:
    if el is None:
        return None
    amount = el.get("data-price-amount")
    if amount:
        try:
            return float(amount)
        except ValueError:
            pass
    text = el.get_text(strip=True).replace("$", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


# --- tallas de la ficha (PDP) -----------------------------------------------
def _parse_sizes(html: str) -> list[str]:
    """Lee las tallas con stock del ``jsonConfig`` embebido en la PDP."""
    soup = BeautifulSoup(html, "lxml")
    for script in soup.select('script[type="text/x-magento-init"]'):
        text = script.string or script.get_text()
        if not text or '"jsonConfig"' not in text:
            continue
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            continue
        for section in data.values():
            if not isinstance(section, dict):
                continue
            for widget in section.values():
                cfg = (widget or {}).get("jsonConfig") if isinstance(widget, dict) else None
                attributes = (cfg or {}).get("attributes") if isinstance(cfg, dict) else None
                if not isinstance(attributes, dict):
                    continue
                for attr in attributes.values():
                    if isinstance(attr, dict) and attr.get("code") == "size":
                        return [
                            str(opt.get("label", "")).strip()
                            for opt in attr.get("options", [])
                            if opt.get("products") and opt.get("label")
                        ]
    return []


# --- caché de fichas -------------------------------------------------------
def _load_cache() -> dict[str, dict]:
    path = config.DETAILS_CONVERSE_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict[str, dict]) -> None:
    path = config.DETAILS_CONVERSE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _is_stale(entry: dict | None, now: datetime) -> bool:
    if not entry:
        return True
    stamp = entry.get("fetched_at")
    if not stamp:
        return True
    try:
        fetched = datetime.fromisoformat(stamp)
    except ValueError:
        return True
    if fetched.tzinfo is None:
        fetched = fetched.replace(tzinfo=timezone.utc)
    return (now - fetched).days >= config.DETAILS_TTL_DAYS
