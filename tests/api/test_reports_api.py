"""Tests de contrato de POST /reports, GET /reports y GET /reports/{id} (TASK-016).

Geometría sintética (cuadrado en lat 1-2, lon -2 a -1) y Muse falso: sin red ni lugares reales.
"""

import io
import json
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from climapp.api.main import create_app, get_settings
from climapp.api.reports import get_muse_client
from climapp.config import Settings
from climapp.verification.muse import MuseError, MuseTask, RecordedMuseClient
from tests.api.contract import assert_matches, documented_statuses
from tests.conftest import rewrite_env
from tests.verification.fakes import ScriptedMuse, reply

SQUARE = [[-2.0, 1.0], [-1.0, 1.0], [-1.0, 2.0], [-2.0, 2.0], [-2.0, 1.0]]
INSIDE = {"lat": "1.5123456", "lon": "-1.4987654"}
OUTSIDE = {"lat": "5.0", "lon": "-1.5"}
TEXT = "Llueve muy fuerte hace una hora y el río viene crecido"
CLAIMS = ["Llueve muy fuerte", "El río viene crecido"]
STRUCTURED = json.dumps(
    {
        "event_type": "lluvia",
        "intensity": "fuerte",
        "observed_at": "2024-12-31T16:30:00-05:00",
        "claims": CLAIMS,
        "numbers_cited": [],
    }
)
VERDICT = json.dumps(
    {"claims": [{"text": c, "evidence": "texto", "supported": True} for c in CLAIMS]}
)


@pytest.fixture
def settings(env_file: Path) -> Settings:
    rewrite_env(env_file, MAX_PHOTO_BYTES="200000")
    loaded = Settings(_env_file=env_file)
    path = loaded.data_dir / loaded.basin_polygon_file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "Polygon", "coordinates": [SQUARE]}), encoding="utf-8")
    return loaded


def _client(settings: Settings, muse: ScriptedMuse) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_muse_client] = lambda: muse
    return TestClient(app)


def _verifying_muse() -> ScriptedMuse:
    return ScriptedMuse({MuseTask.STRUCTURE: [reply(STRUCTURED)], MuseTask.JUDGE: [reply(VERDICT)]})


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with _client(settings, _verifying_muse()) as test_client:
        yield test_client


def _jpeg() -> bytes:
    exif = Image.Exif()
    exif[0x010F] = "FabricanteFalso"
    out = io.BytesIO()
    Image.new("RGB", (16, 16)).save(out, format="JPEG", exif=exif)
    return out.getvalue()


def test_post_returns_202_verifying_and_then_the_report_is_verified(client: TestClient) -> None:
    response = client.post("/reports", data={"text": TEXT, **INSIDE})
    assert response.status_code == 202
    body = response.json()
    assert_matches(body, "Report")
    assert body["status"] == "verificando"
    done = client.get(f"/reports/{body['id']}").json()
    assert_matches(done, "Report")
    assert done["status"] == "verificado"
    assert done["structured"]["claims"] == CLAIMS
    assert done["confidence"]["score"] >= 0
    assert [a["passed"] for a in done["attempts"]] == [True]
    assert done["fallback"] is False


def test_published_coordinates_are_rounded_to_three_decimals(client: TestClient) -> None:
    body = client.post("/reports", data={"text": TEXT, **INSIDE}).json()
    assert (body["lat"], body["lon"]) == (1.512, -1.499)
    assert "text" not in body  # el texto del ciudadano no se publica


def test_outside_the_basin_is_rejected_without_calling_the_llm(settings: Settings) -> None:
    muse = ScriptedMuse({})
    with _client(settings, muse) as client:
        response = client.post("/reports", data={"text": TEXT, **OUTSIDE})
        assert response.status_code == 202
        body = response.json()
        assert (body["status"], body["reject_reason"]) == ("rechazado", "fuera_de_cuenca")
        assert client.get(f"/reports/{body['id']}").json()["status"] == "rechazado"
    assert muse.requests == []


def test_three_failed_attempts_require_human_review(settings: Settings) -> None:
    muse = ScriptedMuse({MuseTask.STRUCTURE: [reply("no es json")] * 3})
    with _client(settings, muse) as client:
        report_id = client.post("/reports", data={"text": TEXT, **INSIDE}).json()["id"]
        done = client.get(f"/reports/{report_id}").json()
    assert done["status"] == "requiere_revision_humana"
    assert [a["reasons"] for a in done["attempts"]] == [["esquema_invalido"]] * 3
    assert done["structured"] is None and done["confidence"] is None


def test_photo_exif_is_removed_before_saving(client: TestClient, settings: Settings) -> None:
    files = {"photo": ("foto.jpg", _jpeg(), "image/jpeg")}
    body = client.post("/reports", data={"text": TEXT, **INSIDE}, files=files).json()
    saved = list((settings.data_dir / settings.photos_dir).glob(f"{body['id']}.*"))
    assert len(saved) == 1
    assert b"FabricanteFalso" not in saved[0].read_bytes()
    assert not Image.open(saved[0]).getexif()


def test_photo_without_text_goes_to_human_review_without_llm(settings: Settings) -> None:
    muse = ScriptedMuse({})
    with _client(settings, muse) as client:
        files = {"photo": ("foto.jpg", _jpeg(), "image/jpeg")}
        body = client.post("/reports", data=INSIDE, files=files).json()
        assert client.get(f"/reports/{body['id']}").json()["status"] == "requiere_revision_humana"
    assert muse.requests == []  # v1 no verifica imágenes con el modelo


@pytest.mark.parametrize(
    ("data", "files"),
    [
        (INSIDE, None),  # sin texto ni foto
        ({"text": TEXT, "lat": "x", "lon": "-1.5"}, None),
        ({"text": "", **INSIDE}, None),
        ({"text": "a" * 1001, **INSIDE}, None),
        ({"text": TEXT, **INSIDE}, {"photo": ("f.jpg", b"x" * 200_001, "image/jpeg")}),  # > MAX
        ({"text": TEXT, **INSIDE}, {"photo": ("f.gif", b"GIF89a" + b"\0" * 30, "image/gif")}),
    ],
)
def test_invalid_input_is_422_entrada_invalida(
    client: TestClient, data: dict[str, str], files: dict[str, tuple[str, bytes, str]] | None
) -> None:
    response = client.post("/reports", data=data, files=files)
    assert response.status_code == 422
    assert_matches(response.json(), "Error")
    assert response.json()["code"] == "entrada_invalida"


def test_without_basin_polygon_post_is_503(settings: Settings) -> None:
    (settings.data_dir / settings.basin_polygon_file).unlink()
    with _client(settings, ScriptedMuse({})) as client:
        response = client.post("/reports", data={"text": TEXT, **INSIDE})
    assert response.status_code == 503
    assert response.json()["code"] == "sin_poligono"


def test_get_unknown_report_is_404(client: TestClient) -> None:
    response = client.get(f"/reports/{uuid4()}")
    assert response.status_code == 404
    assert_matches(response.json(), "Error")
    assert response.json()["code"] == "reporte_no_encontrado"


def test_list_filters_by_status_and_matches_the_contract(client: TestClient) -> None:
    client.post("/reports", data={"text": TEXT, **INSIDE})
    client.post("/reports", data={"text": TEXT, **OUTSIDE})
    verified = client.get("/reports", params={"status": "verificado"}).json()
    assert [r["status"] for r in verified] == ["verificado"]
    for item in client.get("/reports").json():
        assert_matches(item, "ReportSummary")
    assert len(client.get("/reports", params={"limit": 1}).json()) == 1
    assert client.get("/reports", params={"limit": 501}).status_code == 422


def test_every_status_code_is_documented() -> None:
    assert {202, 422, 503} <= documented_statuses("/reports", "post")
    assert {200, 404} <= documented_statuses("/reports/{id}")


def test_muse_failure_sends_the_report_to_human_review(settings: Settings) -> None:
    class Down:
        def complete(self, task: MuseTask, messages: object) -> object:
            raise MuseError("sin red")

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_muse_client] = Down
    with TestClient(app) as client:
        report_id = client.post("/reports", data={"text": TEXT, **INSIDE}).json()["id"]
        assert client.get(f"/reports/{report_id}").json()["status"] == "requiere_revision_humana"


def test_default_client_with_demo_fallback_uses_recordings(env_file: Path) -> None:
    settings = Settings(_env_file=rewrite_env(env_file, DEMO_FALLBACK="1"))
    client = get_muse_client(settings)
    assert isinstance(client, RecordedMuseClient)
    assert get_muse_client(settings) is client  # uno por configuración


# --- privacidad de las afirmaciones (decisión del equipo, 2026-10-31) ----------------

SUMMARY_FIELDS = {
    "event_type",
    "intensity",
    "observed_at",
    "lat",
    "lon",
    "status",
    "confidence",
    "fallback",
}


def test_list_shows_only_structured_fields_without_claims_or_ids(client: TestClient) -> None:
    client.post("/reports", data={"text": TEXT, **INSIDE})
    (item,) = client.get("/reports", params={"status": "verificado"}).json()
    assert set(item) == SUMMARY_FIELDS  # sin id: no se puede llegar al detalle desde la lista
    assert (item["event_type"], item["intensity"]) == ("lluvia", "fuerte")
    assert item["observed_at"].startswith("2024-12-31T16:30")
    assert (item["lat"], item["lon"]) == (1.512, -1.499)
    assert CLAIMS[0] not in json.dumps(item, ensure_ascii=False)


def test_rejected_reports_in_the_list_have_no_structured_fields(client: TestClient) -> None:
    client.post("/reports", data={"text": TEXT, **OUTSIDE})
    (item,) = client.get("/reports", params={"status": "rechazado"}).json()
    assert_matches(item, "ReportSummary")
    assert (item["event_type"], item["confidence"]) == (None, None)


def test_detail_by_id_keeps_the_claims_for_the_sender(client: TestClient) -> None:
    report_id = client.post("/reports", data={"text": TEXT, **INSIDE}).json()["id"]
    assert UUID(report_id).version == 4  # id no adivinable
    detail = client.get(f"/reports/{report_id}").json()
    assert_matches(detail, "Report")
    assert detail["structured"]["claims"] == CLAIMS


def test_claims_with_personal_data_are_rejected_and_retried(settings: Settings) -> None:
    leaky = json.loads(STRUCTURED) | {"claims": ["Llueve fuerte", "Llamen al 300 123 4567"]}
    muse = ScriptedMuse(
        {
            MuseTask.STRUCTURE: [reply(json.dumps(leaky)), reply(STRUCTURED)],
            MuseTask.JUDGE: [reply(VERDICT)],
        }
    )
    with _client(settings, muse) as client:
        report_id = client.post("/reports", data={"text": TEXT, **INSIDE}).json()["id"]
        detail = client.get(f"/reports/{report_id}").json()
    assert [a["reasons"] for a in detail["attempts"]] == [["dato_personal"], []]
    assert detail["status"] == "verificado"
