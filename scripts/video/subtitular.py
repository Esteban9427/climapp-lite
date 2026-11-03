"""Calcula los tiempos de los subtítulos de cada segmento contra su audio final.

Uso (faster-whisper en un entorno aparte):
    uv run --project ~/tools/asr python scripts/video/subtitular.py \
        docs/video/guion.json video/audio 1 2 6 7

El texto sale del guion (``subtitulos``: lo que JM dijo, con los errores de
transcripción corregidos); Whisper solo aporta los tiempos por palabra. Cada
cue toma un tramo de palabras proporcional a su número de palabras.
Escribe ``segNN.cues.json`` con ``[{inicio_s, fin_s, en, es}]``.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel

LOG = logging.getLogger("video.subtitular")
MODELO = "large-v3"


def palabras(modelo: WhisperModel, wav: Path) -> list[tuple[float, float]]:
    """Tiempos (inicio, fin) de cada palabra reconocida en el audio.

    Args:
        modelo: modelo de Whisper cargado.
        wav: audio del segmento.

    Returns:
        Lista de tiempos por palabra, en orden.
    """
    segs, _ = modelo.transcribe(str(wav), language="en", beam_size=5, word_timestamps=True)
    return [(w.start, w.end) for s in segs for w in (s.words or [])]


def alinear(cues: list[dict[str, str]], tiempos: list[tuple[float, float]]) -> list[dict[str, Any]]:
    """Reparte los tiempos de palabra entre los cues según su número de palabras.

    Args:
        cues: subtítulos del guion (``en``/``es``).
        tiempos: tiempos por palabra reconocida.

    Returns:
        Cues con ``inicio_s`` y ``fin_s``.

    Raises:
        ValueError: si no hay palabras reconocidas.
    """
    if not tiempos:
        raise ValueError("Whisper no reconoció palabras en el audio")
    conteos = [len(c["en"].split()) for c in cues]
    escala, acumulado, salida = len(tiempos) / sum(conteos), 0, []
    for cue, n in zip(cues, conteos, strict=True):
        i = min(round(acumulado * escala), len(tiempos) - 1)
        acumulado += n
        j = max(min(round(acumulado * escala), len(tiempos)) - 1, i)
        salida.append(
            {"inicio_s": round(tiempos[i][0], 2), "fin_s": round(tiempos[j][1], 2), **cue}
        )
    return salida


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada: escribe ``segNN.cues.json`` para los segmentos pedidos.

    Args:
        argv: argumentos de línea de comandos.

    Returns:
        Código de salida (0 si todo salió bien).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("guion", type=Path)
    parser.add_argument("audio", type=Path)
    parser.add_argument("ids", type=int, nargs="+")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    guion = json.loads(args.guion.read_text(encoding="utf-8"))
    modelo = WhisperModel(MODELO, device="cpu", compute_type="int8")
    for seg in guion["segmentos"]:
        if seg["id"] not in args.ids or not seg["subtitulos"]:
            continue
        cues = alinear(seg["subtitulos"], palabras(modelo, args.audio / f"seg{seg['id']:02d}.wav"))
        (args.audio / f"seg{seg['id']:02d}.cues.json").write_text(
            json.dumps(cues, indent=1, ensure_ascii=False)
        )
        LOG.info(
            json.dumps({"event": "subtitulos.alineados", "segmento": seg["id"], "cues": len(cues)})
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
