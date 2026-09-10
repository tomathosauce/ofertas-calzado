"""Configuración del monitor de ofertas.

Todos los ajustes viven aquí para no tener que tocar el código de los scrapers.
"""
from __future__ import annotations

from pathlib import Path

# --- Rutas -----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = DATA_DIR / "reports"
TEMPLATES_DIR = BASE_DIR / "templates"

SNAPSHOT_FILE = DATA_DIR / "snapshot.json"
HISTORY_CSV = DATA_DIR / "history.csv"
LATEST_REPORT = REPORTS_DIR / "ofertas_latest.html"
# Caché de tallas por ficha de producto (solo Converse lo necesita).
DETAILS_CONVERSE_FILE = DATA_DIR / "details_converse.json"

# --- Red ----------------------------------------------------------------
# UA "honesto" para las peticiones simples; no incluye datos personales.
USER_AGENT = "ofertas-monitor/1.0 (monitor personal de ofertas de calzado)"
# UA de navegador real: necesario para pasar el reto de Imperva en Converse.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

REQUEST_DELAY = (1.0, 2.0)   # pausa aleatoria (min, max) en segundos entre peticiones
MAX_PAGES = 10               # tope de seguridad de páginas por tienda
RETRIES = 2                  # reintentos ante error de red
HTTP_TIMEOUT = 30.0          # segundos

# --- Filtrado ---------------------------------------------------------------
FOOTWEAR_ONLY = True
# Se aplica al texto de categoría/tipo de cada producto (case-insensitive).
FOOTWEAR_CATEGORY_RE = r"zapatilla|sandalia|calzado|bota|sneaker|tenis"
MIN_DISCOUNT_PCT = 0         # descarta ofertas con descuento menor a este %

# --- Fichas de producto (tallas de Converse) ------------------------------
CONVERSE_FETCH_DETAILS = True   # visitar la PDP de cada producto para leer tallas
DETAILS_TTL_DAYS = 14           # re-consultar una ficha pasados estos días
CONVERSE_PDP_MAX = 200         # tope de seguridad de fichas por corrida

# --- Tiendas --------------------------------------------------------------
STORES = ("converse", "vans")

CONVERSE_SALE_URL = "https://www.converse.com.pa/rebajas-converse.html"
# Alternativa por URL para pedir solo calzado (Magento layered nav).
CONVERSE_FOOTWEAR_FILTER = "type_of_product=1039"

VANS_PRODUCTS_JSON = "https://www.vans.com.pa/collections/sale-eoss/products.json"
VANS_PRODUCT_URL = "https://www.vans.com.pa/products/{handle}"
VANS_FOOTWEAR_TYPE = "CALZADO"
