"""Fotos de los reportes: tamaño, tipo y eliminación de metadatos (EXIF, PRD NFR-7).

La imagen se decodifica y se vuelve a codificar solo con sus píxeles, así que no queda
EXIF (incluida la ubicación GPS) ni texto PNG. Solo se aceptan JPEG y PNG.
"""

import io

from PIL import Image, UnidentifiedImageError

FORMATS = {"JPEG": "jpg", "PNG": "png"}
JPEG_QUALITY = 90  # recodificación: calidad alta para no degradar la evidencia visual
BYTES_PER_MB = 1024 * 1024


class PhotoError(ValueError):
    """La foto no es aceptable (tamaño o tipo)."""


def strip_metadata(raw: bytes, max_bytes: int) -> tuple[bytes, str]:
    """Devuelve la foto sin metadatos y su extensión.

    Args:
        raw: bytes recibidos.
        max_bytes: tamaño máximo (`MAX_PHOTO_BYTES`, 5 MB).

    Raises:
        PhotoError: si supera el tamaño o no es un JPEG o PNG válido.
    """
    if len(raw) > max_bytes:
        msg = f"la foto supera el tamaño máximo ({max_bytes / BYTES_PER_MB:.0f} MB)"
        raise PhotoError(msg)
    try:
        with Image.open(io.BytesIO(raw)) as image:
            kind = image.format or ""
            if kind not in FORMATS:
                msg = "la foto debe ser JPEG o PNG"
                raise PhotoError(msg)
            clean = Image.frombytes(image.mode, image.size, image.tobytes())  # solo píxeles
    except (UnidentifiedImageError, OSError) as err:
        msg = "la foto debe ser JPEG o PNG"
        raise PhotoError(msg) from err
    out = io.BytesIO()
    options = {"quality": JPEG_QUALITY} if kind == "JPEG" else {}
    clean.save(out, format=kind, **options)
    return out.getvalue(), FORMATS[kind]
