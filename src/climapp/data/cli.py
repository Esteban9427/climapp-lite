"""Comando reproducible que regenera la tabla diaria de estaciones (ADR-004 §4).

Uso: `uv run climapp-daily` (lee `.env`; los datos viven en `DATA_DIR`, fuera de git).
"""

from pathlib import Path

from climapp.config import Settings
from climapp.data.daily import DailyConfig, build_station_daily, load_station_map, write_daily_csv
from climapp.data.outages import load_known_outages
from climapp.logging import configure_logging, get_logger

log = get_logger(__name__)


def build_daily(settings: Settings) -> Path:
    """Regenera `DAILY_STATIONS_FILE` a partir de `STATION_EXPORTS`.

    Args:
        settings: configuración; las rutas son relativas a `DATA_DIR`, salvo
            `KNOWN_OUTAGES_FILE`, que está versionado (relativa al directorio actual).

    Returns:
        Ruta del csv escrito.

    Raises:
        ValueError: si una exportación, el mapa de estaciones o el registro de fallas
            no son válidos (`pydantic.ValidationError` es un `ValueError`).
        OSError: si un archivo no se puede leer o escribir.
    """
    data_dir = settings.data_dir
    exports = [data_dir / path for path in settings.station_exports]
    station_map = load_station_map(data_dir / settings.station_map_file)
    outages = load_known_outages(settings.known_outages_file)
    config = DailyConfig.from_settings(settings)
    rows = build_station_daily(exports, station_map, config, outages)
    return write_daily_csv(rows, data_dir / settings.daily_stations_file)


def main() -> None:
    """Punto de entrada de `climapp-daily`."""
    configure_logging()
    out = build_daily(Settings())
    log.info("daily.done", path=str(out))
