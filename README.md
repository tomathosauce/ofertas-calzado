# Monitor de ofertas de calzado — Converse PA + Vans PA

Herramienta de línea de comandos que revisa las páginas de rebajas de
**Converse Panamá** y **Vans Panamá**, se queda **solo con el calzado** y, en cada
ejecución, genera un **reporte HTML** + un **histórico CSV** marcando los productos
**nuevos en oferta** respecto a la corrida anterior.

- Ejecución manual o **automática diaria** con un timer de systemd en Linux.
- Sin notificaciones push: el resultado es el HTML y el CSV en `data/`.

## Instalación

```bash
pip install -r requirements.txt
playwright install chromium
```

`playwright install chromium` hace falta por **Converse**, que está detrás de la
protección Imperva/Incapsula y requiere un navegador real. **Vans** usa el JSON abierto
de Shopify y funciona sin navegador.

## Uso

### Revisión automática (Linux con systemd)

El timer incluido revisa ambas tiendas **todos los días a las 9:00 a. m. de
Panamá**. Si el equipo estaba apagado, ejecuta la revisión pendiente cuando
el timer vuelve a activarse. El equipo necesita conexión a Internet; no se
despierta ni se enciende automáticamente.

Los archivos suponen que el proyecto está en `~/ofertas-calzado` y que sus
dependencias están instaladas en `.venv`. Configura primero GitHub con
`./setup-github.sh`. Si mueves el proyecto, cambia las rutas de ambos archivos
`systemd/*.service` antes de instalarlos.

```bash
mkdir -p ~/.config/systemd/user
cp systemd/*.service systemd/*.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ofertas-calzado.timer
# Permite funcionar después de cerrar sesión y arrancar al encender el equipo:
loginctl enable-linger "$USER"
```

Abre `data/reports/ofertas_latest.html` para consultar el último resultado.
Cada revisión guarda también un reporte fechado y actualiza el CSV histórico.
Las novedades se comparan con la revisión anterior, aunque no hayas abierto
su reporte. Al terminar con un reporte válido, activa un servicio independiente
que publica en **https://tomathosauce.github.io/ofertas-calzado/**.
También publica resultados parciales, con los avisos de las tiendas que fallaron.
Si ninguna tienda responde, conserva el sitio publicado anteriormente.

```bash
# Próxima revisión
systemctl --user list-timers ofertas-calzado.timer
# Revisar ahora (systemd evita dos ejecuciones simultáneas del servicio)
systemctl --user start ofertas-calzado.service
# Estado y registro de las revisiones
systemctl --user status ofertas-calzado.service
systemctl --user status ofertas-calzado-publish.service
journalctl --user -u ofertas-calzado.service -u ofertas-calzado-publish.service -n 80 --no-pager
# Reintentar la publicación sin volver a consultar las tiendas
systemctl --user start ofertas-calzado-publish.service
# Desactivar las revisiones automáticas
systemctl --user disable --now ofertas-calzado.timer
systemctl --user stop ofertas-calzado.service ofertas-calzado-publish.service
```

El servicio limita cada ejecución a 30 minutos. Un fallo total marca el servicio
como fallido; un fallo parcial (salida 2) permite guardar el reporte de las
tiendas que respondieron y deja el aviso en el registro y el reporte.
Cada servicio reintenta sus fallos cada 15 minutos, con un máximo de tres
arranques en dos horas. Publicar tiene un límite de 10 minutos por intento y
sus reintentos reutilizan los reportes, sin repetir el scraping. Después de
agotar los intentos, el siguiente horario diario vuelve a iniciar el flujo.
Los fallos quedan en el journal; no se envían notificaciones.

Para cambiar el horario, edita `OnCalendar` en
`~/.config/systemd/user/ofertas-calzado.timer`, ejecuta
`systemctl --user daemon-reload` y luego
`systemctl --user restart ofertas-calzado.timer`.

### Revisión manual

```bash
python scrape_ofertas.py                 # ambas tiendas -> reporte + CSV + resumen
python scrape_ofertas.py --store vans     # solo una tienda (vans | converse)
python scrape_ofertas.py --store vans --store converse
python scrape_ofertas.py --open           # abre el reporte HTML al terminar
python scrape_ofertas.py --no-report      # solo actualiza el estado y muestra el resumen
python scrape_ofertas.py --no-details     # no visita las fichas de Converse (rápido)
python scrape_ofertas.py --all-products   # incluye ropa y accesorios (desactiva el filtro)
```

Códigos de salida: `0` todo bien · `2` alguna tienda falló o hubo un aviso ·
`1` no se pudo obtener ninguna tienda.

### Velocidad

- **Vans**: unos segundos (JSON).
- **Converse, 1ª corrida**: ~4 min. Visita la ficha de cada producto (~100) para leer
  las tallas y las guarda en `data/details_converse.json`.
- **Converse, corridas siguientes**: ~1 min. Solo consulta la ficha de productos nuevos
  o cuya caché tenga más de `DETAILS_TTL_DAYS` (14 días). `--no-details` la salta del
  todo y usa solo lo que haya en caché.

## El reporte HTML

Autocontenible (doble clic para abrir), tema claro/oscuro. Tres bloques:

1. **🆕 Nuevas ofertas** — tarjetas de lo que no estaba en la corrida anterior.
2. **💲 Bajadas de precio** — productos ya vistos que bajaron de precio (informativo).
3. **Todo el calzado en oferta** — tabla con barra de filtros:
   - **Tienda** · **Género** (Mujer / Hombre / Unisex) · **Edad** (Adulto / Niño).
   - **Talla**: lista única con las tallas reales agrupadas por tienda.
   - **Ordenar**: Descuento, Precio ↑, Precio ↓, Nombre (o clic en cualquier cabecera).
   - Contador "N de M" y "Limpiar filtros".
   - Al pasar el ratón por una fila se ve la **foto** del zapato.

Género y edad se deducen del badge de Converse ("Preescolar…", "Mujer…") y de los tags
de Vans. Se pliega a 3 géneros: Niñas→Mujer, Niños→Hombre, Infante/Preescolar→Unisex;
lo infantil se aísla con el filtro **Edad: Niño**.

## Salida (`data/`)

```
snapshot.json           estado de la última corrida (base de comparación)
details_converse.json   caché de tallas por ficha de Converse
history.csv             una fila por oferta y corrida (append-only)
reports/
  ofertas_<fecha>.html  reporte de esa corrida
  ofertas_latest.html   copia del más reciente
```

- **Primera corrida de una tienda**: guarda su línea base y no marca novedades.
- **Siguientes**: un producto es *nuevo* si su `store:product_id` no estaba en
  `snapshot.json`.
- Si el CSV histórico se creó con una versión anterior (otras columnas), se archiva como
  `history_legacy.csv` y se empieza uno nuevo.
- Columnas del CSV: `run_ts, store, product_id, name, category, gender, age_group, url,
  price, old_price, discount_pct, status` (`status` ∈ `nuevo` | `price_drop` | `existente`).

## Publicar en GitHub Pages

Sitio actual: **https://tomathosauce.github.io/ofertas-calzado/**

`publish.py` copia los reportes a `site/` (lo que Pages sirve). Con `--push`,
prepara y publica el sitio en una copia temporal de `origin/main`, conservando
los reportes que ya estaban publicados. No modifica la rama local ni publica
otros cambios o commits locales. La autenticación la pones tú (`gh auth login`
o un credential helper); el
script no recibe ni maneja tokens.

**Preparación (una vez), ya hecha en este repo:**

```bash
git init && git add -A && git commit -m "init" && git branch -M main
gh repo create ofertas-calzado --public --source=. --remote=origin --push
# El GITHUB_TOKEN del workflow no puede crear el sitio Pages en un repo nuevo,
# así que se habilita una vez con tu propio token (scope repo):
gh api -X POST repos/USUARIO/ofertas-calzado/pages -f build_type=workflow
```

El workflow `.github/workflows/deploy-pages.yml` publica `site/` en cada push que lo
toque (no hace scraping: Converse bloquea las IPs de datacenter, el scraping se queda
en tu equipo).

Para instalar GitHub CLI y configurar la autenticación en Debian/Ubuntu:

```bash
./setup-github.sh
```

Ejecuta el script como tu usuario normal, **sin sudo**. El script solicita sudo
para instalar paquetes y después inicia la autorización de GitHub en el navegador.
Si `gh` ya está instalado, omite la instalación; si ya tienes una sesión válida,
la reutiliza. Configura las credenciales de Git para tu usuario, pero no hace
push ni activa la publicación automática del timer.

**Cada actualización:**

```bash
python scrape_ofertas.py          # o --no-details para ir rápido
python publish.py --push
```

`publish.py` sin `--push` solo regenera `site/` para revisarlo. El último reporte
queda en la raíz y el histórico en `.../reports/`.
La publicación usa commits normales, sin force-push. Si alguien actualiza
`main` durante la publicación y Git rechaza el push, el siguiente intento
parte de la nueva versión remota. Los reportes se conservan localmente para
poder reintentar si falla la conexión.

Notas: el CSV y el snapshot quedan fuera por `.gitignore`; solo se publican reportes
de precios públicos. Las imágenes se enlazan desde los CDN de las tiendas.

## Estructura

```
scrape_ofertas.py          # CLI de scraping
publish.py                 # arma site/ y (--push) lo sube a GitHub Pages
.github/workflows/deploy-pages.yml   # despliegue de site/ a Pages
ofertas/
  config.py                # todos los ajustes
  models.py                # dataclass Offer
  classify.py              # (género, edad) a partir de texto suelto
  state.py                 # snapshot + cálculo de novedades
  report.py                # HTML (Jinja2) + CSV
  stores/
    base.py                # interfaz Store
    converse.py            # Magento 2 + Imperva (httpx -> Chromium persistente) + tallas de la PDP
    vans.py                # Shopify products.json
templates/report.html.j2   # plantilla del reporte
site/                       # salida publicable (generada por publish.py)
```

## Ajustes habituales (`ofertas/config.py`)

| Ajuste | Para qué |
|---|---|
| `FOOTWEAR_ONLY` | activar/desactivar el filtro de calzado |
| `FOOTWEAR_CATEGORY_RE` | palabras que identifican calzado en la categoría (Converse) |
| `MIN_DISCOUNT_PCT` | ocultar ofertas con descuento menor a X % |
| `CONVERSE_FETCH_DETAILS` | visitar las fichas de Converse para leer tallas |
| `DETAILS_TTL_DAYS` | cada cuántos días se refresca una ficha en caché |
| `CONVERSE_PDP_MAX` | tope de fichas a consultar por corrida |
| `REQUEST_DELAY`, `MAX_PAGES`, `RETRIES` | cortesía y robustez de red |

## Notas y límites

- Uso personal y de baja frecuencia: UA identificable, pausas entre peticiones y tope
  de páginas. No hay paralelismo agresivo.
- Las tallas de Converse salen del `jsonConfig` embebido en la ficha; solo incluye las
  tallas con stock.
- Si Imperva pasa a exigir un CAPTCHA visual, Converse se reportará como error; habría
  que ejecutar una vez con `headless=False` en `ofertas/stores/converse.py` para pasar
  la verificación manualmente.
