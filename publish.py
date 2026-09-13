#!/usr/bin/env python3
"""Prepara (y opcionalmente publica) el reporte para GitHub Pages.

Copia los reportes de ``data/reports/`` a ``site/``, que es lo que GitHub Pages
sirve:

    site/index.html             -> el reporte más reciente
    site/reports/<fecha>.html   -> todos los reportes con fecha
    site/reports/index.html     -> índice navegable del histórico
    site/.nojekyll              -> para que Pages no procese nada

Con ``--push`` publica solo los reportes en una copia temporal de origin/main.
La autenticación de git/GitHub la pones tú (``gh auth login`` o un credential
helper); este script nunca recibe ni maneja tokens.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "data" / "reports"
SITE_DIR = ROOT / "site"

_DATED = re.compile(r"^ofertas_(\d{4}-\d{2}-\d{2}_\d{4})\.html$")


def dated_reports(directory: Path = REPORTS_DIR) -> list[Path]:
    files = [p for p in directory.glob("ofertas_*.html") if _DATED.match(p.name)]
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


def build_site(site_dir: Path = SITE_DIR) -> Path:
    reports = dated_reports(REPORTS_DIR)
    if not reports:
        sys.exit(
            f"No hay reportes en {REPORTS_DIR}.\n"
            "Ejecuta primero:  python scrape_ofertas.py"
        )

    site_reports = site_dir / "reports"
    site_reports.mkdir(parents=True, exist_ok=True)

    for src in reports:
        shutil.copyfile(src, site_reports / src.name)

    # Conservar el histórico remoto, incluso si no existe en este equipo.
    reports = dated_reports(site_reports)
    latest = reports[0]
    index_path = site_dir / "index.html"
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
    (site_reports / "index.html").write_text(
        _INDEX_TMPL.format(items="\n".join(items), n=len(reports)), encoding="utf-8"
    )
    (site_dir / ".nojekyll").write_text("", encoding="utf-8")

    print(f"site/ listo · index.html = {latest.name} · {len(reports)} reporte(s)")
    return latest


def _git(*args: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd or ROOT, text=True, capture_output=True,
        timeout=120,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "/bin/false"},
    )
    if result.returncode:
        raise RuntimeError(f"git {args[0]} falló:\n{result.stderr or result.stdout}")
    return result.stdout.strip()


def push(message: str | None = None) -> None:
    # Partir siempre del remoto permite reintentar tras fallos y evita publicar
    # commits o cambios del usuario. Git rechaza avances concurrentes sin forzar.
    remote = _git("remote", "get-url", "--push", "origin")
    identity = {key: _git("config", "--get", key) for key in ("user.name", "user.email")}
    with tempfile.TemporaryDirectory(prefix="ofertas-publish-") as directory:
        checkout = Path(directory) / "repo"
        _git("clone", "--quiet", "--depth", "1", "--single-branch", "--branch", "main",
             "--", remote, str(checkout))
        for key, value in identity.items():
            _git("config", key, value, cwd=checkout)
        latest = build_site(checkout / "site")
        _git("add", "--", "site", cwd=checkout)
        if not _git("diff", "--cached", "--name-only", cwd=checkout):
            print("site/ ya está actualizado en GitHub; nada que publicar.")
            return
        stamp = _DATED.match(latest.name).group(1)
        _git("-c", "commit.gpgsign=false", "commit", "-m",
             message or f"reporte {stamp}", cwd=checkout)
        _git("push", "origin", "HEAD:refs/heads/main", cwd=checkout)
    print("Publicado. El workflow de GitHub Pages actualizará el sitio.")


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

    try:
        if args.push:
            push(args.message)
        else:
            build_site()
    except (RuntimeError, subprocess.TimeoutExpired) as err:
        print(f"Publicación fallida: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
