"""Genera tomas de narración con voz clonada (Chatterbox Multilingual, CPU).

Uso (Chatterbox en un entorno aparte):
    uv run --project ~/tools/voz-tts python scripts/video/narrar.py \
        docs/video/guion.json ~/voz/jm/ref_jm.wav video/audio/clon 3 4 --tomas 3

SOLO con consentimiento escrito de la persona cuya voz se clona y solo para
los segmentos autorizados (ver docs/video/README.md). Usa el texto exacto de
``narracion_en``; genera frase por frase (los textos largos se degradan) y
une las frases con una pausa corta. Escribe ``segNN_tK.wav`` por toma.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path

import torch
import torchaudio as ta
from chatterbox.mtl_tts import ChatterboxMultilingualTTS

LOG = logging.getLogger("video.narrar")
PAUSA_ENTRE_FRASES_S = 0.25
SEMILLA_BASE = 1000


def frases(texto: str) -> list[str]:
    """Divide la narración en frases para generarlas por separado.

    Args:
        texto: narración completa.

    Returns:
        Frases sin espacios sobrantes.
    """
    return [f.strip() for f in re.split(r"(?<=[.?!])\s+", texto) if f.strip()]


def generar_toma(
    modelo: ChatterboxMultilingualTTS, texto: str, ref: Path, semilla: int
) -> torch.Tensor:
    """Genera una toma completa uniendo las frases con una pausa corta.

    Args:
        modelo: modelo cargado.
        texto: narración completa.
        ref: audio de referencia de la voz.
        semilla: semilla de la toma (tomas distintas = semillas distintas).

    Returns:
        Audio (1, n) a ``modelo.sr``.
    """
    torch.manual_seed(semilla)
    pausa = torch.zeros(1, int(modelo.sr * PAUSA_ENTRE_FRASES_S))
    partes: list[torch.Tensor] = []
    for frase in frases(texto):
        wav = modelo.generate(frase, language_id="en", audio_prompt_path=str(ref))
        partes += [wav.cpu(), pausa]
    return torch.cat(partes[:-1], dim=1)


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada: genera ``--tomas`` tomas por segmento pedido.

    Args:
        argv: argumentos de línea de comandos.

    Returns:
        Código de salida (0 si todo salió bien).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("guion", type=Path)
    parser.add_argument("ref", type=Path)
    parser.add_argument("salida", type=Path)
    parser.add_argument("ids", type=int, nargs="+")
    parser.add_argument("--tomas", type=int, default=3)
    parser.add_argument("--primera", type=int, default=1, help="número de la primera toma")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    guion = json.loads(args.guion.read_text(encoding="utf-8"))
    args.salida.mkdir(parents=True, exist_ok=True)
    modelo = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
    for seg in (s for s in guion["segmentos"] if s["id"] in args.ids):
        for k in range(args.primera, args.primera + args.tomas):
            t0 = time.monotonic()
            wav = generar_toma(modelo, seg["narracion_en"], args.ref, SEMILLA_BASE * seg["id"] + k)
            destino = args.salida / f"seg{seg['id']:02d}_t{k}.wav"
            ta.save(str(destino), wav, modelo.sr)
            evento = {"event": "toma.generada", "segmento": seg["id"], "toma": k}
            evento |= {
                "audio_s": round(wav.shape[1] / modelo.sr, 2),
                "cpu_s": round(time.monotonic() - t0, 1),
            }
            LOG.info(json.dumps(evento))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
