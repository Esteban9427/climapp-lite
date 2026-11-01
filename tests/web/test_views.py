"""Tests HTTP del HTML: pronóstico, formulario y lista de reportes (TASK-017, docs/design.md)."""

import re

from climapp.api.main import get_settings
from climapp.api.schemas import Forecast
from climapp.config import Settings
from climapp.verification.explain import VerifiedExplanation
from climapp.verification.muse import MuseTask
from climapp.web.demo import load_demo_reports
from tests.api.test_reports_api import INSIDE, OUTSIDE, TEXT
from tests.conftest import ROOT, env_example_items
from tests.verification.fakes import ScriptedMuse, reply
from tests.web.conftest import OFFICIAL, MakeClient
from tests.web.test_agreement import VERIFIED_LABEL

IDEAM = "https://www.ideam.gov.co/nuestra-entidad/servicio-de-pronosticos-y-alertas"


def test_page_is_mobile_first_spanish_and_uses_the_design_tokens(make_client: MakeClient) -> None:
    html = make_client().get("/").text
    assert '<html lang="es">' in html
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in html
    assert "/static/tokens.css" in html and "/static/vendor/htmx.min.js" in html
    assert html.count("<h1") == 1


def test_disclaimer_with_both_official_channels_is_always_visible(make_client: MakeClient) -> None:
    client = make_client()
    for path in ("/", "/?replay_date=2024-12-31", "/?replay_date=1999-01-01"):
        html = client.get(path).text
        banner = re.search(r'<div class="aviso"[^>]*role="note".*?</div>', html, re.S)
        assert banner, path
        assert "No es una alerta oficial" in banner.group(0)
        assert OFFICIAL in banner.group(0) and IDEAM in banner.group(0)


def test_forecast_card_shows_probability_threshold_and_accumulation(
    make_client: MakeClient,
) -> None:
    html = make_client().get("/").text
    assert "7 %" in html  # 0,07 de la emisión vigente
    assert "20 mm" in html and "50,4 mm" in html
    assert "Reproducción histórica" not in html


def test_replay_is_labelled_and_uses_the_operational_variant(make_client: MakeClient) -> None:
    html = make_client().get("/?replay_date=2024-12-31").text
    assert "Reproducción histórica" in html
    assert "11 %" in html


def test_null_explanation_is_never_replaced_by_unverified_text(make_client: MakeClient) -> None:
    html = make_client().get("/").text
    assert "Sin explicación verificada" in html


def test_verified_explanation_is_shown_with_its_fallback_mark(make_client: MakeClient) -> None:
    def explainer(_: Forecast) -> VerifiedExplanation:
        return VerifiedExplanation(text="Texto verificado de prueba.", fallback=True)

    html = make_client(explainer=explainer).get("/").text
    assert "Texto verificado de prueba." in html
    assert "Verificado por la compuerta" in html and "respuesta grabada" in html


def test_missing_forecast_shows_the_error_state_and_keeps_the_disclaimer(
    make_client: MakeClient, web_settings: Settings
) -> None:
    (web_settings.data_dir / web_settings.forecasts_file).unlink()
    html = make_client().get("/").text
    assert "No hay pronóstico calculado" in html
    assert "No es una alerta oficial" in html


def test_empty_list_state(make_client: MakeClient) -> None:
    assert "Aún no hay reportes verificados" in make_client().get("/").text


def test_form_has_labels_location_and_accepts_only_jpeg_or_png(make_client: MakeClient) -> None:
    html = make_client().get("/").text
    assert 'hx-post="/web/reports"' in html and 'hx-encoding="multipart/form-data"' in html
    assert '<label for="report-text"' in html and '<label for="report-photo"' in html
    assert 'accept="image/jpeg,image/png"' in html
    assert 'name="lat"' in html and 'name="lon"' in html
    assert "Usar mi ubicación" in html
    assert 'aria-live="polite"' in html


def test_submitting_shows_verifying_then_verified_with_confidence(make_client: MakeClient) -> None:
    client = make_client()
    partial = client.post("/web/reports", data={"text": TEXT, **INSIDE}).text
    assert "Verificando tu reporte" in partial
    poll = re.search(r'hx-get="(/web/reports/[0-9a-f-]+/estado)"', partial)
    assert poll and 'hx-trigger="every 2s"' in partial
    done = client.get(poll.group(1)).text
    assert re.search(VERIFIED_LABEL, done)
    assert "hx-trigger" not in done  # el sondeo se detiene en un estado final
    assert "lluvia" in client.get("/").text  # aparece en la lista


def test_outside_basin_shows_the_rejection_reason(make_client: MakeClient) -> None:
    partial = (
        make_client(ScriptedMuse({})).post("/web/reports", data={"text": TEXT, **OUTSIDE}).text
    )
    assert "Rechazado: la ubicación está fuera de la cuenca del río Pance" in partial


def test_human_review_state_lists_the_reasons(make_client: MakeClient) -> None:
    muse = ScriptedMuse({MuseTask.STRUCTURE: [reply("no es json")] * 3})
    client = make_client(muse)
    partial = client.post("/web/reports", data={"text": TEXT, **INSIDE}).text
    report_id = re.search(r"/web/reports/([0-9a-f-]+)/estado", partial)
    assert report_id
    done = client.get(f"/web/reports/{report_id.group(1)}/estado").text
    assert "En revisión humana (no pasó la verificación tras 3 intentos)" in done
    assert "esquema_invalido" in done and "formato esperado" in done


def test_invalid_input_shows_an_error_message(make_client: MakeClient) -> None:
    response = make_client().post("/web/reports", data=INSIDE)
    assert response.status_code == 200  # HTMX reemplaza el contenido; el error va en el HTML
    assert "Envía un texto o una foto" in response.text


def test_unknown_report_status_shows_the_error_state(make_client: MakeClient) -> None:
    html = make_client().get("/web/reports/00000000-0000-4000-8000-000000000000/estado").text
    assert "No se pudo consultar el estado" in html


def test_demo_examples_are_offered_only_in_fallback_mode(
    make_client: MakeClient, web_settings: Settings
) -> None:
    assert "Ejemplos de la demo" not in make_client().get("/").text
    demo = web_settings.model_copy(update={"demo_fallback": True})
    app_client = make_client()
    app_client.app.dependency_overrides[get_settings] = lambda: demo  # type: ignore[attr-defined]
    html = app_client.get("/").text
    assert "Ejemplos de la demo" in html
    examples = load_demo_reports(ROOT / env_example_items()["DEMO_REPORTS_FILE"])
    for example in examples:
        assert f'data-text="{example.text}"' in html
    point = (demo.demo_example_lat, demo.demo_example_lon)  # cauce del río (OSM)
    assert f'data-lat="{point[0]}"' in html and f'data-lon="{point[1]}"' in html


def test_replay_shows_imerg_early_of_the_issue_and_target_days(
    make_client: MakeClient, web_settings: Settings
) -> None:
    """TASK-009b: en la reproducción se ve el satélite de esos días, si existe."""
    path = web_settings.data_dir / web_settings.imerg_early_file
    path.write_text("date,precip_mm\n2024-12-31,5.085\n", encoding="utf-8")
    html = make_client().get("/?replay_date=2024-12-31").text
    assert "IMERG Early" in html
    assert "2024-12-31: 5,1 mm" in html and "2025-01-01: sin dato" in html
    assert "IMERG Early" not in make_client().get("/").text  # en vivo no se muestra


def test_replay_without_imerg_file_says_nothing_about_it(make_client: MakeClient) -> None:
    assert "IMERG Early" not in make_client().get("/?replay_date=2024-12-31").text
