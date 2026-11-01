"""`climapp-demo-reset`: vacía los reportes de la base local para empezar la demo de cero.

Pide escribir `BORRAR` antes de borrar (o `--yes`). Borra también las fotos guardadas de
esos reportes. Solo toca `DATA_DIR`, que está fuera de git.
"""

import sys
from collections.abc import Callable, Sequence

from climapp.api.store import ReportStore
from climapp.config import Settings
from climapp.logging import configure_logging, get_logger

log = get_logger(__name__)
CONFIRMATION = "BORRAR"


def main(argv: Sequence[str] | None = None, answer: Callable[[str], str] = input) -> int:
    """Vacía la base de reportes tras la confirmación; devuelve el código de salida.

    Args:
        argv: argumentos (`--yes` evita la pregunta); por defecto, los de la línea de comandos.
        answer: función que lee la respuesta (en los tests, un doble).

    Returns:
        0 si se vació la base; 1 si no se confirmó.
    """
    configure_logging()
    args = list(sys.argv[1:] if argv is None else argv)
    settings = Settings()
    path = settings.data_dir / settings.reports_db_file
    if (
        "--yes" not in args
        and answer(f"Escribe {CONFIRMATION} para vaciar {path}: ") != CONFIRMATION
    ):
        log.info("demo_reset.cancelled", path=str(path))
        return 1
    removed = ReportStore(path, settings.local_timezone).clear()
    photos = settings.data_dir / settings.photos_dir
    for record in removed:
        if record.photo_file:
            (photos / record.photo_file).unlink(missing_ok=True)
    log.info("demo_reset.done", path=str(path), removed=len(removed))
    return 0


def cli() -> None:
    """Punto de entrada de `climapp-demo-reset`."""
    sys.exit(main())
