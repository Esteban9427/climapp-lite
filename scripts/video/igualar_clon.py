"""Iguala una toma de voz clonada al sonido de los audios reales.

Uso:
    uv run python scripts/video/igualar_clon.py docs/video/guion.json \
        video/audio/clon/seg03_t3.wav video/audio/seg03_clon.wav \
        --referencias video/audio/seg01.wav video/audio/seg06.wav video/audio/seg07.wav \
        [--fin-s 21.95]

Aplica el mismo tratamiento que ``preparar_audio`` (silencios, pausas, tempo,
loudnorm), recorta opcionalmente un artefacto al final, elige un realce de
agudos suave para acercar el centroide espectral al de las referencias reales
y deja la toma en los LUFS exactos del guion.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import statistics
import sys
from pathlib import Path
from typing import Any

from preparar_audio import SAMPLE_RATE, ejecutar, filtro_audio, igualar_sonoridad

LOG = logging.getLogger("video.igualar_clon")
GANANCIAS_AGUDOS_DB = (0, 1, 2, 3, 4, 5, 6)  # SUPUESTO: más de 6 dB suena artificial
FRECUENCIA_AGUDOS_HZ = 2500
FUNDIDO_FIN_S = 0.15


def centroide(ruta: Path, filtro: str = "anull") -> float:
    """Mediana del centroide espectral (Hz) en tramos con voz.

    Args:
        ruta: audio a medir.
        filtro: filtro previo a la medición (para probar un EQ sin escribirlo).

    Returns:
        Centroide mediano en Hz.

    Raises:
        RuntimeError: si ffmpeg falla o no hay tramos con voz.
    """
    log = ejecutar(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(ruta), "-af",
         f"{filtro},aspectralstats=measure=centroid,ametadata=print:file=-", "-f", "null", "-"]
    )  # fmt: skip
    valores = [v for v in (float(x) for x in re.findall(r"centroid=([\d.]+)", log)) if v > 0]
    if not valores:
        raise RuntimeError(f"no se pudo medir el centroide de {ruta.name}")
    return statistics.median(valores)


def elegir_agudos(ruta: Path, objetivo: float) -> int:
    """Elige el realce de agudos que más acerca el centroide al objetivo.

    Args:
        ruta: toma ya procesada.
        objetivo: centroide de las referencias reales (Hz).

    Returns:
        Ganancia en dB del shelf de agudos.
    """

    def distancia(g: int) -> float:
        filtro = f"treble=g={g}:f={FRECUENCIA_AGUDOS_HZ}" if g else "anull"
        return abs(centroide(ruta, filtro) - objetivo)

    return min(GANANCIAS_AGUDOS_DB, key=distancia)


def procesar(guion: dict[str, Any], toma: Path, destino: Path, fin_s: float | None) -> None:
    """Aplica el tratamiento de los audios reales y el recorte final opcional.

    Args:
        guion: guion completo.
        toma: WAV crudo de Chatterbox.
        destino: WAV procesado.
        fin_s: si se indica, corta ahí (en tiempo ya procesado) con un fundido corto.

    Raises:
        RuntimeError: si ffmpeg falla.
    """
    ret, salida = guion["retemporizado"], guion["salida"]
    filtro = filtro_audio({"recortar_silencio": True}, ret, salida["lufs"])
    if fin_s is not None:
        filtro += f",atrim=0:{fin_s},afade=t=out:st={fin_s - FUNDIDO_FIN_S}:d={FUNDIDO_FIN_S}"
    ejecutar(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(toma), "-af", filtro,
         "-ac", "1", "-ar", str(SAMPLE_RATE), str(destino)]
    )  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada: procesa, iguala timbre y sonoridad, y registra el resultado.

    Args:
        argv: argumentos de línea de comandos.

    Returns:
        Código de salida (0 si todo salió bien).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("guion", type=Path)
    parser.add_argument("toma", type=Path)
    parser.add_argument("destino", type=Path)
    parser.add_argument("--referencias", type=Path, nargs="+", required=True)
    parser.add_argument("--fin-s", type=float, default=None)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    guion = json.loads(args.guion.read_text(encoding="utf-8"))
    procesar(guion, args.toma, args.destino, args.fin_s)
    objetivo = statistics.median(centroide(r) for r in args.referencias)
    agudos = elegir_agudos(args.destino, objetivo)
    if agudos:
        tmp = args.destino.with_suffix(".eq.wav")
        filtro = f"treble=g={agudos}:f={FRECUENCIA_AGUDOS_HZ}"
        ejecutar(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(args.destino),
                  "-af", filtro, str(tmp)])  # fmt: skip
        tmp.replace(args.destino)
    ganancia = igualar_sonoridad(args.destino, guion["salida"]["lufs"])
    evento = {"event": "clon.igualado", "destino": str(args.destino), "agudos_db": agudos}
    evento |= {"centroide_obj": round(objetivo), "centroide": round(centroide(args.destino))}
    LOG.info(json.dumps(evento | {"ganancia_db": ganancia}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
