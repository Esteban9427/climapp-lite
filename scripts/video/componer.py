"""Arma el MP4 final del video de demo a partir del guion, audios y clips.

Uso:
    uv run python scripts/video/componer.py docs/video/guion.json ~/voz/jm video

Lee ``video/audio/segNN.wav`` + ``segNN.cues.json`` y ``video/clips/segNN.mp4``.
Cada segmento dura su audio + ``relleno_s`` (la tarjeta final, su duración
fija). Escribe ``video/subtitulos_{en,es}.srt``, quema los subtítulos en
inglés, normaliza a ``salida.lufs`` en dos pasadas y exporta
``video/climapp-lite-demo.mp4`` (H.264 -preset veryfast -crf 20, 1920x1080).
Falla si la duración total supera ``limite_total_s``.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOG = logging.getLogger("video.componer")
FPS = 30
FONDO = "0x0f172a"
BORDE = "0x334155"
TEXTO_TENUE = "0x94a3b8"
TELEFONO_ALTO = 1000
VELOCIDAD_CLIP_MAX = 1.35  # SUPUESTO: más rápido el scroll deja de leerse
FUNDIDO_S = 0.3
TITULO_CORTO = 30  # caracteres que caben en una línea a 84 px


@dataclass(frozen=True)
class Plan:
    """Segmento listo para renderizar."""

    seg: dict[str, Any]
    duracion: float
    inicio: float
    retraso: float
    cues: list[dict[str, Any]]


def ejecutar(cmd: list[str]) -> str:
    """Ejecuta un comando sin shell y devuelve stdout + stderr.

    Args:
        cmd: comando y argumentos.

    Returns:
        Salida combinada (ffmpeg informa por stderr).

    Raises:
        RuntimeError: si el comando falla.
    """
    # Comando fijo armado aquí, sin shell; las rutas vienen del guion versionado.
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    if res.returncode != 0:
        raise RuntimeError(f"{cmd[0]} falló: {res.stderr.strip()[-800:]}")
    return res.stdout + res.stderr


def duracion(ruta: Path) -> float:
    """Duración en segundos medida con ffprobe.

    Args:
        ruta: archivo de audio o video.

    Returns:
        Duración en segundos.

    Raises:
        RuntimeError: si ffprobe falla.
    """
    salida = ejecutar(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(ruta)]
    )
    return float(salida.strip())


def planificar(guion: dict[str, Any], audio: Path) -> list[Plan]:
    """Calcula duración, inicio y subtítulos de cada segmento.

    Args:
        guion: guion completo.
        audio: carpeta con ``segNN.wav`` y ``segNN.cues.json``.

    Returns:
        Planes en orden de aparición.

    Raises:
        ValueError: si el total supera ``limite_total_s``.
    """
    planes, t, relleno = [], 0.0, guion["relleno_s"]
    for seg in guion["segmentos"]:
        n = seg["id"]
        if seg["audio"] is None:
            dur, cues = float(seg["pantalla"]["duracion_s"]), []
        else:
            dur = duracion(audio / f"seg{n:02d}.wav") + relleno
            cues = json.loads((audio / f"seg{n:02d}.cues.json").read_text(encoding="utf-8"))
        planes.append(Plan(seg, round(dur, 3), round(t, 3), relleno / 2, cues))
        t += dur
    if t > guion["limite_total_s"]:
        raise ValueError(f"duración total {t:.1f} s supera {guion['limite_total_s']} s")
    return planes


def texto(tmp: Path, nombre: str, contenido: str, ancho: int) -> str:
    """Escribe un texto envuelto en un archivo para ``drawtext=textfile``.

    Args:
        tmp: carpeta temporal.
        nombre: nombre del archivo.
        contenido: texto a mostrar.
        ancho: caracteres por línea.

    Returns:
        Ruta del archivo, lista para el filtro.
    """
    ruta = tmp / f"{nombre}.txt"
    ruta.write_text("\n".join(textwrap.wrap(contenido, ancho)), encoding="utf-8")
    return str(ruta)


def dibujar(archivo: str, fuente: str, tam: int, pos: tuple[str, str], extra: str = "") -> str:
    """Filtro ``drawtext`` con estilo común.

    Args:
        archivo: ruta del ``textfile``.
        fuente: ruta de la fuente.
        tam: tamaño en px.
        pos: expresiones de posición (x, y).
        extra: opciones adicionales (``:clave=valor``).

    Returns:
        Filtro listo para encadenar.
    """
    return (
        f"drawtext=fontfile='{fuente}':textfile='{archivo}':fontsize={tam}:fontcolor=white"
        f":line_spacing={tam // 3}:x={pos[0]}:y={pos[1]}{extra}"
    )


def video_tarjeta(p: Plan, cfg: dict[str, Any], tmp: Path) -> str:
    """Filtro de video para tarjetas (fila 1, 7 y la final).

    Args:
        p: plan del segmento.
        cfg: bloque ``salida`` del guion.
        tmp: carpeta temporal.

    Returns:
        Cadena de filtros que parte de ``[0:v]`` (fondo).
    """
    pant, n = p.seg["pantalla"], p.seg["id"]
    final = pant["tipo"] == "tarjeta_final"
    textos = pant.get("textos") or [pant["texto"]]
    tam, ancho = (46, 60) if final else (84 if max(map(len, textos)) <= TITULO_CORTO else 64, 48)
    cambio = (
        p.cues[pant["cambio_en_cue"]]["inicio_s"] + p.retraso if len(textos) > 1 else p.duracion
    )
    filtros = []
    for i, txt in enumerate(textos):
        ventana = f"between(t,0,{cambio})" if i == 0 else f"gte(t,{cambio})"
        archivo = texto(tmp, f"tarjeta{n}_{i}", txt, ancho)
        fuente = cfg["fuente_texto"] if final else cfg["fuente_titulo"]
        extra = f":text_align=C:enable='{ventana}'"
        filtros.append(dibujar(archivo, fuente, tam, ("(w-text_w)/2", "(h-text_h)/2-60"), extra))
    return "[0:v]" + ",".join(filtros)


def video_camara(p: Plan, cfg: dict[str, Any], insumos: Path, tmp: Path) -> tuple[list[str], str]:
    """Entradas y filtro para el clip a cámara (fila 2), al tempo del audio.

    Args:
        p: plan del segmento.
        cfg: bloque ``salida`` del guion.
        insumos: carpeta con los originales.
        tmp: carpeta temporal.

    Returns:
        Argumentos de entrada extra y cadena de filtros.
    """
    pant, tempo = p.seg["pantalla"], cfg["tempo"]
    rotulo = texto(tmp, "rotulo2", pant["rotulo"], 80)
    filtro = (
        f"[1:v]setpts=PTS/{tempo},fps={FPS},scale=1440:810,"
        f"tpad=start_duration={p.retraso}:start_mode=clone:stop_mode=clone:stop_duration=5,"
        f"trim=duration={p.duracion},setpts=PTS-STARTPTS[cam];"
        f"[0:v][cam]overlay=(W-w)/2:60,"
        + dibujar(
            rotulo,
            cfg["fuente_titulo"],
            36,
            ("270", "100"),
            ":box=1:boxcolor=0x0f172acc:boxborderw=18",
        )
    )
    return ["-i", str(insumos / pant["fuente"])], filtro


def video_pantalla(p: Plan, cfg: dict[str, Any], clips: Path, tmp: Path) -> tuple[list[str], str]:
    """Entradas y filtro para un clip de pantalla en vista móvil centrada.

    Args:
        p: plan del segmento.
        cfg: bloque ``salida`` del guion.
        clips: carpeta con ``segNN.mp4`` y ``segNN.json``.
        tmp: carpeta temporal.

    Returns:
        Argumentos de entrada extra y cadena de filtros.
    """
    n = p.seg["id"]
    clip = clips / f"seg{n:02d}.mp4"
    marcas = json.loads((clips / f"seg{n:02d}.json").read_text(encoding="utf-8"))
    inicio = p.seg["pantalla"].get("clip_inicio_s", marcas[0]["t_s"])
    vel = min(max((duracion(clip) - inicio) / p.duracion, 1.0), VELOCIDAD_CLIP_MAX)
    titulo = texto(tmp, f"titulo{n}", p.seg["seccion"], 18)
    marca = texto(tmp, f"marca{n}", "ClimApp Lite", 40)
    filtro = (
        f"[1:v]trim=start={inicio},setpts=(PTS-STARTPTS)/{vel:.4f},fps={FPS},"
        f"scale=-2:{TELEFONO_ALTO},pad=iw+8:ih+8:4:4:color={BORDE},"
        f"tpad=stop_mode=clone:stop_duration={p.duracion},trim=duration={p.duracion}[tel];"
        f"[0:v][tel]overlay=(W-w)/2:(H-h)/2,"
        + dibujar(marca, cfg["fuente_texto"], 30, ("90", "(h/2)-150"), f":fontcolor={TEXTO_TENUE}")
        + ","
        + dibujar(titulo, cfg["fuente_titulo"], 56, ("90", "(h/2)-100"))
    )
    LOG.info(json.dumps({"event": "clip.ajustado", "segmento": n, "velocidad": round(vel, 3)}))
    return ["-i", str(clip)], filtro


def render_segmento(p: Plan, guion: dict[str, Any], rutas: dict[str, Path]) -> Path:
    """Renderiza un segmento (video + audio sin pérdida) a ``tmp/segNN.mkv``.

    Args:
        p: plan del segmento.
        guion: guion completo.
        rutas: carpetas ``audio``, ``clips``, ``insumos`` y ``tmp``.

    Returns:
        Ruta del segmento renderizado.

    Raises:
        RuntimeError: si ffmpeg falla.
    """
    n, tipo, tmp = p.seg["id"], p.seg["pantalla"]["tipo"], rutas["tmp"]
    cfg = {**guion["salida"], "tempo": guion["retemporizado"]["tempo"]}
    fondo = ["-f", "lavfi", "-i", f"color=c={FONDO}:s=1920x1080:r={FPS}:d={p.duracion}"]
    entradas: list[str] = []
    if tipo == "camara":
        entradas, vf = video_camara(p, cfg, rutas["insumos"], tmp)
    elif tipo in ("app", "web"):
        entradas, vf = video_pantalla(p, cfg, rutas["clips"], tmp)
    else:
        vf = video_tarjeta(p, cfg, tmp)
    fundido = f"fade=in:st=0:d={FUNDIDO_S},fade=out:st={p.duracion - FUNDIDO_S}:d={FUNDIDO_S}"
    vf += f",{fundido},format=yuv420p[v]"
    idx_audio = 1 + len(entradas) // 2
    if p.seg["audio"] is None:
        audio_in, af = ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono"], f"[{idx_audio}:a]"
    else:
        audio_in, af = ["-i", str(rutas["audio"] / f"seg{n:02d}.wav")], f"[{idx_audio}:a]"
    af += f"adelay={int(p.retraso * 1000)}:all=1,apad=whole_dur={p.duracion}"
    af += f",atrim=duration={p.duracion}[a]"
    salida = tmp / f"seg{n:02d}.mkv"
    ejecutar(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            *fondo,
            *entradas,
            *audio_in,
            "-filter_complex",
            f"{vf};{af}",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-t",
            str(p.duracion),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "14",
            "-c:a",
            "pcm_s16le",
            str(salida),
        ]
    )
    LOG.info(json.dumps({"event": "segmento.renderizado", "segmento": n, "duracion_s": p.duracion}))
    return salida


def marca_tiempo(t: float, ass: bool) -> str:
    """Formatea segundos como tiempo SRT (``00:00:01,500``) o ASS (``0:00:01.50``).

    Args:
        t: segundos.
        ass: True para formato ASS.

    Returns:
        Tiempo formateado.
    """
    cs = round(t * 100) if ass else round(t * 1000)
    if ass:
        return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"
    return f"{cs // 3600000:02d}:{cs // 60000 % 60:02d}:{cs // 1000 % 60:02d},{cs % 1000:03d}"


def cues_globales(planes: list[Plan]) -> list[tuple[float, float, str, str]]:
    """Subtítulos con tiempos absolutos; cada cue dura hasta el siguiente si hay hueco corto.

    Args:
        planes: segmentos planificados.

    Returns:
        Lista de (inicio, fin, en, es).
    """
    salida = []
    for p in planes:
        base = p.inicio + p.retraso
        for i, c in enumerate(p.cues):
            fin = p.cues[i + 1]["inicio_s"] if i + 1 < len(p.cues) else c["fin_s"] + 0.2
            salida.append((base + c["inicio_s"], base + max(fin, c["fin_s"]), c["en"], c["es"]))
    return salida


def escribir_subtitulos(planes: list[Plan], salida: Path, cfg: dict[str, Any]) -> Path:
    """Escribe ``subtitulos_{en,es}.srt`` y el ASS en inglés para quemar.

    Args:
        planes: segmentos planificados.
        salida: carpeta ``video/``.
        cfg: bloque ``salida`` del guion.

    Returns:
        Ruta del archivo ASS.
    """
    cues = cues_globales(planes)
    for idioma, k in (("en", 2), ("es", 3)):
        bloques = [
            f"{i}\n{marca_tiempo(c[0], False)} --> {marca_tiempo(c[1], False)}\n{c[k]}\n"
            for i, c in enumerate(cues, 1)
        ]
        (salida / f"subtitulos_{idioma}.srt").write_text("\n".join(bloques), encoding="utf-8")
    cabecera = (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 0\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour,"
        " Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n"
        f"Style: Default,{cfg['fuente_subtitulos']},46,&H00FFFFFF,&H00000000,&H66000000,"
        "-1,4,14,0,2,300,300,48\n\n[Events]\nFormat: Layer, Start, End, Style, Text\n"
    )
    eventos = [
        f"Dialogue: 0,{marca_tiempo(a, True)},{marca_tiempo(b, True)},Default,{en}"
        for a, b, en, _ in cues
    ]
    ass = salida / "tmp" / "subtitulos_en.ass"
    ass.write_text(cabecera + "\n".join(eventos) + "\n", encoding="utf-8")
    return ass


def medir_sonoridad(entrada: Path, lufs: int) -> dict[str, str]:
    """Primera pasada de loudnorm: mide el audio concatenado.

    Args:
        entrada: lista de concatenación.
        lufs: objetivo.

    Returns:
        Medidas de loudnorm (``input_i``, ``input_tp``...).
    """
    log = ejecutar(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(entrada),
            "-vn",
            "-af",
            f"loudnorm=I={lufs}:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ]
    )
    medidas: dict[str, str] = json.loads(log[log.rindex("{") : log.rindex("}") + 1])
    return medidas


def exportar(lista: Path, ass: Path, destino: Path, lufs: int) -> None:
    """Concatena, quema subtítulos y normaliza el audio (segunda pasada).

    Args:
        lista: lista de concatenación de segmentos.
        ass: subtítulos ASS en inglés.
        destino: MP4 de salida.
        lufs: objetivo.

    Raises:
        RuntimeError: si ffmpeg falla.
    """
    m = medir_sonoridad(lista, lufs)
    norm = (
        f"loudnorm=I={lufs}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
        f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
        f":offset={m['target_offset']}:linear=true,aresample=48000"
    )
    ejecutar(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lista),
            "-vf",
            f"ass='{ass}'",
            "-af",
            norm,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(FPS),
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(destino),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    """Punto de entrada: planifica, renderiza segmentos, subtítulos y exporta.

    Args:
        argv: argumentos de línea de comandos.

    Returns:
        Código de salida (0 si todo salió bien).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("guion", type=Path)
    parser.add_argument("insumos", type=Path)
    parser.add_argument("video", type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    guion = json.loads(args.guion.read_text(encoding="utf-8"))
    rutas = {
        "audio": args.video / "audio",
        "clips": args.video / "clips",
        "insumos": args.insumos,
        "tmp": args.video / "tmp",
    }
    rutas["tmp"].mkdir(parents=True, exist_ok=True)
    planes = planificar(guion, rutas["audio"])
    segmentos = [render_segmento(p, guion, rutas) for p in planes]
    lista = rutas["tmp"] / "concat.txt"
    lista.write_text("".join(f"file '{s.resolve()}'\n" for s in segmentos), encoding="utf-8")
    ass = escribir_subtitulos(planes, args.video, guion["salida"])
    destino = args.video / "climapp-lite-demo.mp4"
    exportar(lista, ass, destino, guion["salida"]["lufs"])
    tabla = [
        {"segmento": p.seg["id"], "inicio_s": p.inicio, "duracion_s": p.duracion} for p in planes
    ]
    (rutas["tmp"] / "plan.json").write_text(json.dumps(tabla, indent=1), encoding="utf-8")
    LOG.info(
        json.dumps(
            {
                "event": "video.exportado",
                "ruta": str(destino),
                "duracion_s": round(duracion(destino), 2),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
