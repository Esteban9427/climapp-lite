"""Prepara la narración: WAV 48 kHz mono, pausas acortadas, tempo y loudnorm.

Uso:
    uv run python scripts/video/preparar_audio.py \
        docs/video/guion.json ~/voz/jm video/audio [ids...]

Para cada segmento con ``audio`` lee su ``fuente`` (m4a o el clip a cámara),
y según ``retemporizado`` del guion:
- si ``recortar_silencio``: quita el silencio de los extremos y acorta las
  pausas internas a ``pausa_max_s`` (no sirve en clips a cámara: rompe la
  sincronía con los labios);
- aplica ``tempo`` (nunca más de ``tempo_max``) y normaliza a ``salida.lufs``.
Escribe ``segNN.wav`` y registra su duración en JSON. No toca los originales.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

LOG = logging.getLogger("video.audio")
SAMPLE_RATE = 48_000
PICO_MAX_DBTP = -1.5  # mismo techo que el loudnorm del video final


def filtro_audio(seg_audio: dict[str, Any], ret: dict[str, Any], lufs: int) -> str:
    """Cadena ``-af`` de ffmpeg para un segmento.

    Args:
        seg_audio: bloque ``audio`` del segmento.
        ret: bloque ``retemporizado`` del guion.
        lufs: sonoridad objetivo (LUFS integrados).

    Returns:
        Filtro listo para ffmpeg.

    Raises:
        ValueError: si el tempo pedido supera ``tempo_max``.
    """
    if ret["tempo"] > ret["tempo_max"]:
        raise ValueError(f"tempo {ret['tempo']} supera el máximo {ret['tempo_max']}")
    umbral = f"{ret['umbral_silencio_db']}dB"
    partes: list[str] = []
    if seg_audio["recortar_silencio"]:
        inicio = f"silenceremove=start_periods=1:start_threshold={umbral}:start_silence=0.05"
        pausas = (
            f"silenceremove=stop_periods=-1:stop_threshold={umbral}"
            f":stop_duration={ret['pausa_max_s']}:stop_silence={ret['pausa_max_s']}"
        )
        partes += [inicio, "areverse", inicio, "areverse", pausas]
    partes += [
        f"atempo={ret['tempo']}",
        f"loudnorm=I={lufs}:TP=-1.5:LRA=11",
        f"aresample={SAMPLE_RATE}",
    ]
    return ",".join(partes)


def ejecutar(cmd: list[str]) -> str:
    """Ejecuta un comando y devuelve su salida estándar.

    Args:
        cmd: comando y argumentos.

    Returns:
        Salida estándar y de error, sin espacios al final (ffmpeg mide por stderr).

    Raises:
        RuntimeError: si el comando falla.
    """
    # Comando fijo armado aquí, sin shell; las rutas vienen del guion versionado.
    resultado = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    if resultado.returncode != 0:
        raise RuntimeError(f"{cmd[0]} falló: {resultado.stderr.strip()[-500:]}")
    return (resultado.stdout + resultado.stderr).strip()


def duracion(ruta: Path) -> float:
    """Duración en segundos medida con ffprobe.

    Args:
        ruta: archivo de audio o video.

    Returns:
        Duración en segundos.

    Raises:
        RuntimeError: si ffprobe falla.
    """
    return float(
        ejecutar(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(ruta),
            ]
        )
    )


def preparar(seg: dict[str, Any], guion: dict[str, Any], entrada: Path, salida: Path) -> float:
    """Convierte el audio de un segmento y devuelve su duración final.

    Args:
        seg: segmento del guion con bloque ``audio``.
        guion: guion completo (lee ``retemporizado`` y ``salida``).
        entrada: carpeta con los insumos originales.
        salida: carpeta de los WAV.

    Returns:
        Duración del WAV generado, en segundos.

    Raises:
        RuntimeError: si ffmpeg falla.
    """
    destino = salida / f"seg{seg['id']:02d}.wav"
    filtro = filtro_audio(seg["audio"], guion["retemporizado"], guion["salida"]["lufs"])
    ejecutar(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(entrada / seg["audio"]["fuente"]),
            "-vn",
            "-af",
            filtro,
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            str(destino),
        ]
    )
    igualar_sonoridad(destino, guion["salida"]["lufs"])
    return duracion(destino)


def sonoridad(ruta: Path) -> tuple[float, float]:
    """Mide sonoridad integrada (LUFS) y pico verdadero (dBTP) con ebur128.

    Args:
        ruta: audio a medir.

    Returns:
        (LUFS integrados, pico verdadero en dBTP).

    Raises:
        RuntimeError: si ffmpeg falla o no reporta la medida.
    """
    log = ejecutar(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(ruta), "-af", "ebur128=peak=true",
         "-f", "null", "-"]
    )  # fmt: skip
    integrada = re.findall(r"I:\s+(-?[\d.]+) LUFS", log)
    pico = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", log)
    if not integrada or not pico:
        raise RuntimeError(f"ebur128 no reportó sonoridad para {ruta.name}")
    return float(integrada[-1]), float(pico[-1])


def igualar_sonoridad(ruta: Path, lufs: float) -> float:
    """Lleva el audio a ``lufs`` exactos con ganancia lineal (sin compresión).

    El loudnorm de una pasada queda corto en clips de ~20 s (-19 a -21 LUFS);
    una ganancia medida deja todos los segmentos, reales y clonados, al mismo
    nivel. Si el pico pasara de ``PICO_MAX_DBTP``, aplica un limitador suave.

    Args:
        ruta: WAV a corregir en su lugar.
        lufs: objetivo.

    Returns:
        Ganancia aplicada en dB.

    Raises:
        RuntimeError: si ffmpeg falla.
    """
    actual, pico = sonoridad(ruta)
    ganancia = round(lufs - actual, 2)
    filtro = f"volume={ganancia}dB"
    if pico + ganancia > PICO_MAX_DBTP:
        filtro += f",alimiter=limit={10 ** (PICO_MAX_DBTP / 20):.3f}:level=false"
    tmp = ruta.with_suffix(".tmp.wav")
    ejecutar(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(ruta), "-af", filtro,
         "-ar", str(SAMPLE_RATE), str(tmp)]
    )  # fmt: skip
    tmp.replace(ruta)
    return ganancia


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada: prepara los segmentos pedidos (todos si no se indican).

    Args:
        argv: argumentos de línea de comandos.

    Returns:
        Código de salida (0 si todo salió bien).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("guion", type=Path)
    parser.add_argument("entrada", type=Path)
    parser.add_argument("salida", type=Path)
    parser.add_argument("ids", type=int, nargs="*")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    guion = json.loads(args.guion.read_text(encoding="utf-8"))
    args.salida.mkdir(parents=True, exist_ok=True)
    for seg in guion["segmentos"]:
        # Los segmentos con voz clonada los produce igualar_clon.py.
        omitir = seg["audio"] is None or seg["audio"].get("clon", False)
        if omitir or (args.ids and seg["id"] not in args.ids):
            continue
        dur = preparar(seg, guion, args.entrada, args.salida)
        LOG.info(
            json.dumps(
                {"event": "audio.preparado", "segmento": seg["id"], "duracion_s": round(dur, 2)}
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
