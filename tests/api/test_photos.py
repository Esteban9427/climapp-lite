"""Tests de la limpieza de fotos: EXIF eliminado, tamaño y tipo (TASK-016, PRD NFR-7)."""

import io

import pytest
from PIL import Image

from climapp.api.photos import PhotoError, strip_metadata

MAX = 200_000


def _jpeg_with_gps() -> bytes:
    image = Image.new("RGB", (32, 32), (120, 140, 160))
    exif = Image.Exif()
    exif[0x010F] = "FabricanteFalso"  # Make
    exif[0x8825] = {1: "N", 2: (1.0, 2.0, 3.0)}  # GPSInfo sintético
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def test_exif_and_gps_are_removed_from_jpeg() -> None:
    raw = _jpeg_with_gps()
    assert Image.open(io.BytesIO(raw)).getexif()  # el original sí trae EXIF
    clean, ext = strip_metadata(raw, MAX)
    assert ext == "jpg"
    reopened = Image.open(io.BytesIO(clean))
    assert not reopened.getexif()
    assert b"FabricanteFalso" not in clean
    assert reopened.size == (32, 32)


def test_png_text_metadata_is_removed() -> None:
    from PIL import PngImagePlugin

    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "ubicacion-secreta")
    out = io.BytesIO()
    Image.new("RGB", (8, 8)).save(out, format="PNG", pnginfo=info)
    clean, ext = strip_metadata(out.getvalue(), MAX)
    assert ext == "png"
    assert b"ubicacion-secreta" not in clean


def test_photo_over_the_limit_is_rejected() -> None:
    with pytest.raises(PhotoError, match="5 MB|tamaño"):
        strip_metadata(b"x" * (MAX + 1), MAX)


@pytest.mark.parametrize("payload", [b"no es una imagen", b"GIF89a" + b"\x00" * 20])
def test_non_jpeg_png_is_rejected(payload: bytes) -> None:
    with pytest.raises(PhotoError):
        strip_metadata(payload, MAX)
