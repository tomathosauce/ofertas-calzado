#!/usr/bin/env python3
"""Prepara (y opcionalmente publica) el reporte para GitHub Pages.

Copia los reportes de ``data/reports/`` a ``site/``, que es lo que GitHub Pages
sirve:

    site/index.html             -> el reporte más reciente
    site/reports/<fecha>.html   -> todos los reportes con fecha
    site/reports/index.html     -> índice navegable del histórico
    site/.nojekyll              -> para que Pages no procese nada

Con ``--push`` hace además ``git add site`` + ``git commit`` + ``git push``.
La autenticación de git/GitHub la pones tú (``gh auth login`` o un credential
helper); este script nunca recibe ni maneja tokens.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "data" / "reports"
SITE_DIR = ROOT / "site"
SITE_REPORTS = SITE_DIR / "reports"

_DATED = re.compile(r"^ofertas_(\d{4}-\d{2}-\d{2}_\d{4})\.html$")


def dated_reports() -> list[Path]:
    files = [p for p in REPORTS_DIR.glob("ofertas_*.html") if _DATED.match(p.name)]
    return sorted(files, key=lambda p: p.name, reverse=True)


_INDEX_TMPL = """<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Histórico de reportes</title>
<style>
 body{{font:15px/1.6 -apple-system,"Segoe UI",Roboto,Arial,sans-serif;
      max-width:640px;margin:40px auto;padding:0 20px;color-scheme:light dark}}
 h1{{font-size:20px}} a{{color:#1769ff}} ul{{padding-left:18px}}
</style></head><body>
<h1>Histórico de reportes ({n})</h1>
<p><a href="../index.html">&larr; Último reporte</a></p>
<ul>
{items}
</ul>
</body></html>
"""


def build_site() -> Path:
    reports = dated_reports()
    if not reports:
        sys.exit(
            f"No hay reportes en {REPORTS_DIR}.\n"
            "Ejecuta primero:  python scrape_ofertas.py"
        )

    SITE_REPORTS.mkdir(parents=True, exist_ok=True)

    # Quitar de site/reports los HTML que ya no existan en data/reports.
    keep = {p.name for p in reports}
    for old in SITE_REPORTS.glob("ofertas_*.html"):
        if old.name not in keep:
            old.unlink()

    for src in reports:
        shutil.copyfile(src, SITE_REPORTS / src.name)

    latest = reports[0]
    index_path = SITE_DIR / "index.html"
    shutil.copyfile(latest, index_path)
    # Enlace flotante al histórico dentro del reporte publicado.
    _NAV = (
        '<a href="reports/" style="position:fixed;right:14px;bottom:14px;'
        "font:13px/1 -apple-system,Segoe UI,Roboto,sans-serif;background:#1769ff;"
        "color:#fff;padding:7px 13px;border-radius:8px;text-decoration:none;"
        'z-index:99">Histórico &rarr;</a>'
    )
    page = index_path.read_text(encoding="utf-8")
    if 'href="reports/"' not in page:
        index_path.write_text(
            page.replace("</body>", _NAV + "\n</body>", 1), encoding="utf-8"
        )

    items = []
    for path in reports:
        stamp = _DATED.match(path.name).group(1)
        when = dt.datetime.strptime(stamp, "%Y-%m-%d_%H%M")
        items.append(
            f'  <li><a href="{html.escape(path.name)}">'
            f"{when:%d/%m/%Y %H:%M}</a></li>"
        )
    (SITE_REPORTS / "index.html").write_text(
        _INDEX_TMPL.format(items="\n".join(items), n=len(reports)), encoding="utf-8"
    )
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")

    print(f"site/ listo · index.html = {latest.name} · {len(reports)} reporte(s)")
    return latest


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)


def push(message: str) -> None:
    if not (ROOT / ".git").is_dir():
        sys.exit(
            "Todavía no es un repo git. Prepáralo una sola vez:\n"
            "  git init\n"
            "  git add -A && git commit -m \"init\"\n"
            "  git branch -M main\n"
            "  git remote add origin https://github.com/USUARIO/REPO.git\n"
            "  git push -u origin main\n"
            "Luego, en GitHub: Settings -> Pages -> Source = GitHub Actions.\n"
            "Después vuelve a ejecutar:  python publish.py --push"
        )
    if not _git("remote").stdout.strip():
        sys.exit("El repo no tiene remoto. Añádelo:  git remote add origin <URL>")

    _git("add", "site")
    if not _git("status", "--porcelain", "site").stdout.strip():
        print("site/ sin cambios; nada que publicar.")
        return

    done = _git("commit", "-m", message)
    if done.returncode != 0:
        sys.exit(f"git commit falló:\n{done.stderr or done.stdout}")

    done = _git("push")
    if done.returncode != 0:
        sys.exit(
            "git push falló (probablemente autenticación). Configura tu acceso a "
            "GitHub (por ejemplo `gh auth login`) y reintenta.\n"
            + (done.stderr or done.stdout)
        )
    print("Publicado. GitHub Pages actualizará el sitio en ~1 minuto.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="publish", description="Prepara site/ para GitHub Pages."
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="git add/commit/push de site/ (usa tu propia autenticación de git)",
    )
    parser.add_argument("-m", "--message", help="mensaje de commit")
    args = parser.parse_args(argv)

    latest = build_site()
    if args.push:
        stamp = _DATED.match(latest.name).group(1)
        push(args.message or f"reporte {stamp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
