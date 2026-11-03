"""Graba un clip de pantalla por segmento del guion con Playwright.

Uso (Playwright en un entorno aparte, sin ``playwright install``):
    uv run --project ~/tools/video python scripts/video/grabar.py \
        docs/video/guion.json video/clips 3 4 5 6

Ejecuta las ``acciones`` de cada segmento con viewport móvil y escribe
``segNN.webm`` más ``segNN.json`` (marcas de tiempo de cada acción).
Requiere el servidor de la demo en ``captura.base_url`` (127.0.0.1).
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeout

LOG = logging.getLogger("video.grabar")
ESCALA_VIDEO = 2  # el screencast se graba a 2x del viewport (780x1688)
TIMEOUT_RESULTADO_MS = 60_000
NUEVO_RESULTADO_JS = """() => {
  const r = document.querySelector('#report-status .result');
  if (!r || r.innerText === window.__ultimoResultado) return false;
  window.__ultimoResultado = r.innerText;
  return true;
}"""
RESALTE_JS = """(el, acumular) => {
  if (!acumular) document.querySelectorAll('[data-resaltado]').forEach(e => {
    e.style.outline = ''; e.removeAttribute('data-resaltado'); });
  el.setAttribute('data-resaltado', '1');
  el.style.outline = '4px solid #f59e0b';
  el.style.outlineOffset = '4px';
  el.style.borderRadius = '6px';
}"""
TOQUE_JS = """el => {
  const r = el.getBoundingClientRect();
  const d = document.createElement('div');
  const x = r.left + r.width / 2 - 22, y = r.top + r.height / 2 - 22;
  d.style.cssText = `position:fixed;left:${x}px;top:${y}px;
    width:44px;height:44px;border-radius:50%;background:rgba(245,158,11,.45);z-index:99999;
    pointer-events:none;transition:transform .5s,opacity .5s`;
  document.body.appendChild(d);
  requestAnimationFrame(() => { d.style.transform = 'scale(1.6)'; d.style.opacity = '0'; });
  setTimeout(() => d.remove(), 700);
}"""


def ejecutar(page: Page, accion: dict[str, Any], base_url: str) -> None:
    """Ejecuta una acción del guion sobre la página.

    Args:
        page: página de Playwright.
        accion: dict con ``op`` y sus parámetros.
        base_url: raíz de la app de la demo.

    Raises:
        ValueError: si la operación no existe.
        PlaywrightTimeout: si un selector o un resultado no aparece a tiempo.
    """
    op = accion["op"]
    if op in ("goto", "goto_url"):
        url = base_url + accion["ruta"] if op == "goto" else accion["url"]
        page.goto(url, wait_until="networkidle")
    elif op == "wait":
        page.wait_for_timeout(accion["ms"])
    elif op == "scroll":
        page.locator(accion["selector"]).first.evaluate(
            "el => el.scrollIntoView({behavior: 'smooth', block: 'center', inline: 'center'})"
        )
        page.wait_for_timeout(900)
    elif op == "resaltar":
        page.locator(accion["selector"]).first.evaluate(RESALTE_JS, accion.get("acumular", False))
    elif op == "click":
        objetivo = page.locator(accion["selector"]).first
        objetivo.scroll_into_view_if_needed()
        objetivo.evaluate(TOQUE_JS)
        objetivo.click()
    elif op == "esperar_resultado":
        # Espera un resultado nuevo: el del reporte previo sigue visible un instante.
        page.wait_for_function(NUEVO_RESULTADO_JS, timeout=TIMEOUT_RESULTADO_MS)
    else:
        raise ValueError(f"operación desconocida en el guion: {op}")


def grabar_segmento(
    browser: Browser, seg: dict[str, Any], captura: dict[str, Any], salida: Path
) -> None:
    """Graba un segmento en su propio contexto y guarda video y marcas.

    Args:
        browser: navegador abierto.
        seg: segmento del guion.
        captura: bloque ``captura`` del guion.
        salida: carpeta de salida.

    Raises:
        PlaywrightTimeout: si alguna acción no se completa.
    """
    ancho, alto = captura["viewport"]
    tmp = salida / f"tmp{seg['id']:02d}"
    contexto = browser.new_context(
        viewport={"width": ancho, "height": alto},
        device_scale_factor=captura["device_scale_factor"],
        is_mobile=True,
        has_touch=True,
        color_scheme="light",
        locale="es-CO",
        record_video_dir=str(tmp),
        record_video_size={"width": ancho * ESCALA_VIDEO, "height": alto * ESCALA_VIDEO},
    )
    page = contexto.new_page()
    t0, marcas = time.monotonic(), []
    for accion in seg["acciones"]:
        ejecutar(page, accion, captura["base_url"])
        marcas.append({"op": accion["op"], "t_s": round(time.monotonic() - t0, 2)})
    video = page.video
    contexto.close()
    if video is None:
        raise RuntimeError(f"el segmento {seg['id']} no produjo video")
    shutil.move(video.path(), salida / f"seg{seg['id']:02d}.webm")
    shutil.rmtree(tmp, ignore_errors=True)
    (salida / f"seg{seg['id']:02d}.json").write_text(json.dumps(marcas, indent=1))
    LOG.info(
        json.dumps(
            {
                "event": "clip.grabado",
                "segmento": seg["id"],
                "acciones": len(marcas),
                "duracion_s": marcas[-1]["t_s"],
            }
        )
    )


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada: graba los segmentos pedidos que tengan acciones.

    Args:
        argv: argumentos de línea de comandos.

    Returns:
        Código de salida (0 si todo salió bien, 1 si alguna acción falló).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("guion", type=Path)
    parser.add_argument("salida", type=Path)
    parser.add_argument("ids", type=int, nargs="+")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    guion = json.loads(args.guion.read_text(encoding="utf-8"))
    args.salida.mkdir(parents=True, exist_ok=True)
    segmentos = [s for s in guion["segmentos"] if s["id"] in args.ids and s["acciones"]]
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for seg in segmentos:
                grabar_segmento(browser, seg, guion["captura"], args.salida)
        except PlaywrightTimeout as exc:
            LOG.error(json.dumps({"event": "clip.fallo", "error": str(exc).splitlines()[0]}))
            return 1
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
