"""Tests del cliente IMERG Early diario por OPeNDAP de GES DISC (TASK-009b, ADR-002 §4).

Servidor falso con `httpx.MockTransport`: nunca sale a la red. Celda y valores sintéticos.
"""

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

import httpx
import pytest

from climapp.config import Settings
from climapp.data.imerg import (
    ImergClient,
    ImergConfig,
    ImergError,
    cell_index,
    parse_ascii,
    read_imerg_csv,
    update_imerg_early,
)
from tests.conftest import rewrite_env

BASE = "https://imerg.example/opendap/GPM_3IMERGDE.07"
CONFIG = ImergConfig(
    base_url=BASE,
    versions=("V07C", "V07B"),
    grid_deg=0.1,
    retries=3,
    backoff_s=0.0,
    timeout_s=5.0,
)
CELL = (1033, 933)  # (lon, lat) de una celda sintética
SQUARE = [[-76.70, 3.30], [-76.60, 3.30], [-76.60, 3.40], [-76.70, 3.40], [-76.70, 3.30]]


def _ascii(value: float) -> str:
    return (
        "Dataset: 3B-DAY-E.MS.MRG.3IMERG.20261001-S000000-E235959.V07C.nc4\n"
        "precipitation.lat, 3.35\n"
        f"precipitation.precipitation[precipitation.time=17070][precipitation.lon=-76.65], {value}\n"
    )


Handler = Callable[[httpx.Request], httpx.Response]


def _client(
    handler: Handler, token: str = "token-falso"
) -> tuple[ImergClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return ImergClient(CONFIG, token, transport=httpx.MockTransport(record)), seen


def test_cell_index_is_the_0_1_degree_cell_that_contains_the_point() -> None:
    assert cell_index(3.3175, -76.606, 0.1) == CELL
    assert cell_index(-90.0, -180.0, 0.1) == (0, 0)


def test_parse_ascii_reads_the_single_value_and_treats_fill_as_missing() -> None:
    assert parse_ascii(_ascii(7.545)) == pytest.approx(7.545)
    assert parse_ascii(_ascii(-9999.9)) is None
    with pytest.raises(ImergError, match="respuesta"):
        parse_ascii("<html>login</html>")


def test_requests_only_the_basin_cell_with_the_bearer_token() -> None:
    client, seen = _client(lambda _: httpx.Response(200, text=_ascii(18.465)))
    assert client.fetch(date(2026, 10, 2), CELL) == pytest.approx(18.465)
    (request,) = seen
    assert request.headers["Authorization"] == "Bearer token-falso"
    url = str(request.url)
    assert url.startswith(f"{BASE}/2026/10/3B-DAY-E.MS.MRG.3IMERG.20261002-S000000-E235959.V07C")
    assert url.endswith(".nc4.ascii?precipitation%5B0%5D%5B1033%5D%5B933%5D")


def test_falls_back_to_the_next_file_version_on_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(404)
            if "V07C" in str(request.url)
            else httpx.Response(200, text=_ascii(1.0))
        )

    client, seen = _client(handler)
    assert client.fetch(date(2026, 10, 2), CELL) == 1.0
    assert ["V07C" in str(r.url) for r in seen] == [True, False]


def test_day_not_published_yet_is_none() -> None:
    client, _ = _client(lambda _: httpx.Response(404))
    assert client.fetch(date(2026, 11, 1), CELL) is None


def test_retries_transient_errors_then_succeeds() -> None:
    answers = iter(
        [httpx.Response(503), httpx.ConnectError("caída"), httpx.Response(200, text=_ascii(2.5))]
    )

    def handler(_: httpx.Request) -> httpx.Response:
        answer = next(answers)
        if isinstance(answer, Exception):
            raise answer
        return answer

    client, seen = _client(handler)
    assert client.fetch(date(2026, 10, 2), CELL) == 2.5
    assert len(seen) == 3


def test_gives_up_after_the_retries_with_context() -> None:
    client, seen = _client(lambda _: httpx.Response(503))
    with pytest.raises(ImergError, match="2026-10-02"):
        client.fetch(date(2026, 10, 2), CELL)
    assert len(seen) == CONFIG.retries


def test_bad_token_fails_without_retrying() -> None:
    client, seen = _client(lambda _: httpx.Response(401))
    with pytest.raises(ImergError, match="EARTHDATA_TOKEN"):
        client.fetch(date(2026, 10, 2), CELL)
    assert len(seen) == 1


# --- caché y comando ---------------------------------------------------------------


@pytest.fixture
def imerg_settings(env_file: Path, tmp_path: Path) -> Settings:
    rewrite_env(env_file, EARTHDATA_TOKEN="token-falso", IMERG_DAYS="3")
    settings = Settings(_env_file=env_file)
    basin = settings.data_dir / settings.basin_polygon_file
    basin.parent.mkdir(parents=True, exist_ok=True)
    basin.write_text(json.dumps({"type": "Polygon", "coordinates": [SQUARE]}), encoding="utf-8")
    return settings


def test_update_writes_the_last_n_days_and_reuses_the_cache(imerg_settings: Settings) -> None:
    values = {"20261029": 0.2, "20261030": 4.0, "20261031": 33.46}
    client, seen = _client(
        lambda r: httpx.Response(200, text=_ascii(values[str(r.url).split("3IMERG.")[1][:8]]))
    )
    out = update_imerg_early(imerg_settings, date(2026, 11, 1), client)
    assert read_imerg_csv(out) == {
        date(2026, 10, 29): pytest.approx(0.2),
        date(2026, 10, 30): pytest.approx(4.0),
        date(2026, 10, 31): pytest.approx(33.46),
    }
    assert len(seen) == 3
    update_imerg_early(imerg_settings, date(2026, 11, 1), client)
    assert len(seen) == 3  # todo en caché: ninguna petición nueva


def test_missing_days_are_not_cached_and_old_days_are_kept(imerg_settings: Settings) -> None:
    published = {"20261029": 1.0, "20261030": 2.0}

    def handler(request: httpx.Request) -> httpx.Response:
        day = str(request.url).split("3IMERG.")[1][:8]
        return (
            httpx.Response(200, text=_ascii(published[day]))
            if day in published
            else httpx.Response(404)
        )

    client, seen = _client(handler)
    out = update_imerg_early(imerg_settings, date(2026, 11, 1), client)
    assert date(2026, 10, 31) not in read_imerg_csv(out)
    published["20261031"] = 3.0
    update_imerg_early(imerg_settings, date(2026, 11, 2), client)
    cached = read_imerg_csv(out)
    assert cached[date(2026, 10, 29)] == 1.0  # fuera de la ventana nueva, pero se conserva
    assert cached[date(2026, 10, 31)] == 3.0
    assert sum("20261031" in str(r.url) for r in seen) == 3  # 2 versiones el día 1, 1 el día 2


def test_without_token_the_command_refuses(imerg_settings: Settings, env_file: Path) -> None:
    settings = Settings(_env_file=rewrite_env(env_file, EARTHDATA_TOKEN=""))
    with pytest.raises(ImergError, match="EARTHDATA_TOKEN"):
        ImergClient.from_settings(settings)
    assert imerg_settings.imerg_days == 3
