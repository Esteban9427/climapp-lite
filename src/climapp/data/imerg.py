"""IMERG Early diario (GPM_3IMERGDE V07) en la celda de la cuenca, por OPeNDAP (TASK-009b).

Cada día se pide **una sola celda** de 0,1° (la que contiene el centro del polígono de la
cuenca) con la respuesta `.ascii` de OPeNDAP de GES DISC: unos 190 bytes, nunca el archivo
global. El token de Earthdata (`EARTHDATA_TOKEN`) va como `Bearer`. El día de IMERG es UTC
(00:00-23:59 UTC); se guarda con esa fecha (ADR-004 §1). Solo es evidencia satelital de los
reportes (ADR-002 §4): **no entra al modelo**, que está congelado.

Uso: `uv run climapp-imerg` (lee `.env`; escribe `IMERG_EARLY_FILE` en `DATA_DIR`).
"""

import csv
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

from climapp.config import Settings
from climapp.logging import configure_logging, get_logger
from climapp.verification.basin import load_basin

log = get_logger(__name__)
FILE_NAME = "3B-DAY-E.MS.MRG.3IMERG.{ymd}-S000000-E235959.{version}.nc4"
LON_MIN, LAT_MIN = -180.0, -90.0
HTTP_OK, HTTP_NOT_FOUND = 200, 404
AUTH_FAILURES = (401, 403)
Cell = tuple[int, int]  # (índice de longitud, índice de latitud)


class ImergError(Exception):
    """Falla al obtener IMERG Early (credencial, red o respuesta inesperada)."""


@dataclass(frozen=True, slots=True)
class ImergConfig:
    """Parámetros del servicio, normalmente tomados de `Settings`.

    Attributes:
        base_url: raíz OPeNDAP de `GPM_3IMERGDE.07` (`IMERG_OPENDAP_URL`).
        versions: sufijos de versión del archivo, en orden de preferencia.
        grid_deg: tamaño de la celda en grados (0,1° en IMERG).
        retries: intentos por petición ante errores transitorios.
        backoff_s: espera entre intentos, que crece con cada intento.
        timeout_s: tiempo máximo de cada petición.
    """

    base_url: str
    versions: tuple[str, ...]
    grid_deg: float
    retries: int
    backoff_s: float
    timeout_s: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "ImergConfig":
        """Toma las claves `IMERG_*`."""
        return cls(
            base_url=settings.imerg_opendap_url.rstrip("/"),
            versions=tuple(settings.imerg_file_versions),
            grid_deg=settings.imerg_grid_deg,
            retries=settings.imerg_retries,
            backoff_s=settings.imerg_backoff_s,
            timeout_s=settings.imerg_timeout_s,
        )


def cell_index(lat: float, lon: float, grid_deg: float) -> Cell:
    """Índices `(lon, lat)` de la celda de la malla global que contiene el punto."""
    return math.floor((lon - LON_MIN) / grid_deg), math.floor((lat - LAT_MIN) / grid_deg)


def parse_ascii(text: str) -> float | None:
    """Valor de la única celda de una respuesta `.ascii`; negativo (relleno) es `None`.

    Raises:
        ImergError: si la respuesta no trae el valor de `precipitation`.
    """
    lines = [line for line in text.splitlines() if line.startswith("precipitation.precipitation")]
    if not lines:
        msg = "respuesta de OPeNDAP sin valor de precipitation"
        raise ImergError(msg)
    try:
        value = float(lines[0].rsplit(",", 1)[1])
    except (IndexError, ValueError) as err:
        msg = f"respuesta de OPeNDAP ilegible: {lines[0][:80]}"
        raise ImergError(msg) from err
    return value if value >= 0 else None


def _final(response: httpx.Response) -> bool:
    """`True` si la respuesta es definitiva (200 o 404); `False` si conviene reintentar.

    Raises:
        ImergError: si GES DISC rechaza el token (401 o 403); no se reintenta.
    """
    if response.status_code in AUTH_FAILURES:
        msg = f"GES DISC rechazó el token ({response.status_code}): revisa EARTHDATA_TOKEN"
        raise ImergError(msg)
    return response.status_code in (HTTP_OK, HTTP_NOT_FOUND)


class ImergClient:
    """Cliente OPeNDAP de una celda con reintentos (servidor falso en los tests)."""

    def __init__(
        self,
        config: ImergConfig,
        token: str,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Prepara el cliente HTTP con el token como `Bearer`."""
        self._config, self._sleep = config, sleep
        headers = {"Authorization": f"Bearer {token}"}
        self._http = httpx.Client(headers=headers, timeout=config.timeout_s, transport=transport)

    @classmethod
    def from_settings(cls, settings: Settings) -> "ImergClient":
        """Cliente real con `EARTHDATA_TOKEN`.

        Raises:
            ImergError: si `EARTHDATA_TOKEN` está vacío.
        """
        token = settings.earthdata_token.get_secret_value()
        if not token:
            msg = "EARTHDATA_TOKEN vacío: IMERG Early necesita el token de Earthdata"
            raise ImergError(msg)
        return cls(ImergConfig.from_settings(settings), token)

    def _url(self, day: date, version: str, cell: Cell) -> str:
        """URL `.ascii` que pide solo la celda `cell` del día."""
        name = FILE_NAME.format(ymd=day.strftime("%Y%m%d"), version=version)
        query = f"precipitation%5B0%5D%5B{cell[0]}%5D%5B{cell[1]}%5D"
        return f"{self._config.base_url}/{day:%Y/%m}/{name}.ascii?{query}"

    def _get(self, url: str, day: date) -> httpx.Response | None:
        """GET con reintentos; `None` si el archivo no existe (404)."""
        for attempt in range(1, self._config.retries + 1):
            try:
                response = self._http.get(url)
            except httpx.TransportError as err:
                log.warning("imerg.retry", day=str(day), attempt=attempt, error=type(err).__name__)
            else:
                if _final(response):
                    return response if response.status_code == HTTP_OK else None
                log.warning(
                    "imerg.retry", day=str(day), attempt=attempt, status=response.status_code
                )
            if attempt < self._config.retries:
                self._sleep(self._config.backoff_s * attempt)
        msg = f"IMERG Early del {day.isoformat()} no respondió tras {self._config.retries} intentos"
        raise ImergError(msg)

    def fetch(self, day: date, cell: Cell) -> float | None:
        """Lluvia (mm/día UTC) de la celda; `None` si el día aún no está publicado.

        Raises:
            ImergError: credencial rechazada, red caída tras los reintentos o respuesta rara.
        """
        for version in self._config.versions:
            response = self._get(self._url(day, version, cell), day)
            if response is not None:
                return parse_ascii(response.text)
        return None


def write_imerg_csv(values: Mapping[date, float], path: Path) -> Path:
    """Escribe `date,precip_mm` en orden de fecha y devuelve la ruta."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "precip_mm"])
        writer.writerows((day.isoformat(), mm) for day, mm in sorted(values.items()))
    return path


def read_imerg_csv(path: Path) -> dict[date, float]:
    """Lee la serie escrita por `write_imerg_csv`.

    Raises:
        OSError: si el archivo no se puede leer.
        KeyError, ValueError: si falta una columna o un valor no es válido.
    """
    with path.open(encoding="utf-8", newline="") as handle:
        return {
            date.fromisoformat(r["date"]): float(r["precip_mm"]) for r in csv.DictReader(handle)
        }


def update_imerg_early(settings: Settings, today: date, client: ImergClient) -> Path:
    """Agrega a `IMERG_EARLY_FILE` los últimos `IMERG_DAYS` días anteriores a `today`.

    Los días ya guardados no se vuelven a pedir (caché) y los que aún no están
    publicados no se guardan, así que se piden en la próxima corrida.

    Raises:
        ImergError: si el servicio falla.
        BasinError: si falta el polígono de la cuenca.
        OSError: si el archivo no se puede leer o escribir.
    """
    path = settings.data_dir / settings.imerg_early_file
    cached = read_imerg_csv(path) if path.exists() else {}
    lat, lon = load_basin(settings.data_dir / settings.basin_polygon_file).center()
    cell = cell_index(lat, lon, settings.imerg_grid_deg)
    days = [today - timedelta(days=n) for n in range(settings.imerg_days, 0, -1)]
    for day in (d for d in days if d not in cached):
        value = client.fetch(day, cell)
        if value is not None:
            cached[day] = value
    log.info("imerg.written", days=len(cached), latest=max(cached, default=None))
    return write_imerg_csv(cached, path)


def main() -> None:
    """Punto de entrada de `climapp-imerg`."""
    configure_logging()
    settings = Settings()
    today = datetime.now(settings.local_timezone).date()
    update_imerg_early(settings, today, ImergClient.from_settings(settings))
