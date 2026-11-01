"""Tests de contrato de GET /forecast y GET /evaluation (TASK-015)."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from climapp.api.main import (
    DISCLAIMER,
    create_app,
    disclaimer_text,
    get_explainer,
    get_now,
    get_settings,
)
from climapp.api.schemas import Forecast
from climapp.config import Settings
from climapp.verification.explain import VerifiedExplanation, build_explainer
from tests.api.contract import assert_matches, documented_statuses
from tests.conftest import rewrite_env

OFFICIAL = "https://example.org/canales-oficiales"
IDEAM = "https://www.ideam.gov.co/nuestra-entidad/servicio-de-pronosticos-y-alertas"


def _forecast(variant: str, issue: str, target: str, prob: float) -> dict[str, object]:
    return {
        "variant": variant,
        "issue_date": issue,
        "target_date": target,
        "issued_at": f"{target}T00:00:00-05:00",
        "prob_ge_threshold": prob,
        "accum_3d_mm": 50.4,
        "accum_3d_level": "normal",
        "inputs_available": ["EST-A", "EST-C"],
        "model_version": "abc123",
    }


FORECASTS = [
    _forecast("operativa", "2024-12-31", "2025-01-01", 0.11),
    _forecast("operativa", "2026-10-22", "2026-10-23", 0.07),
    _forecast("historica", "2024-12-31", "2025-01-01", 0.15),
]


def _metrics(name: str, variant: str | None, calibrated: bool | None) -> dict[str, object]:
    return {
        "name": name,
        "variant": variant,
        "calibrated": calibrated,
        "available_live": None if variant is None else variant == "operativa",
        "note": None,
        "pod": 0.5,
        "far": 0.8,
        "csi": 0.15,
        "brier": 0.097,
        "auc": 0.66,
        "reliability": [{"bin": "0.0-0.1", "forecast": 0.05, "observed": 0.06, "n": 900}],
        "threshold": 0.11,
        "n_days": 1388,
        "excluded_imputed_days": 0,
    }


EVALUATION = {
    "test_period": {"start": "2023-01-01", "end": "2026-10-31"},
    "target_rule": "basin_mean",
    "threshold_mm": 20.0,
    "data_plan": "plan_b_earthdata",
    "scenarios": {
        "con_est_b": [
            _metrics("rf", "operativa", True),
            _metrics("climatology", None, None),
            _metrics("persistence", None, None),
        ],
        "sin_est_b": [],
    },
    "sensitivity": None,
    "imerg_final_vs_early": None,
    "daily": [{"date": "2025-01-01", "prob": 0.11, "observed": False, "outcome": "falsa_alarma"}],
    "daily_variant": "operativa",
    "excluded_imputed_days": 0,
}


@pytest.fixture
def settings(env_file: Path) -> Settings:
    rewrite_env(env_file, OFFICIAL_CHANNELS_URL=OFFICIAL)
    loaded = Settings(_env_file=env_file)
    out = loaded.data_dir
    (out / "derived").mkdir(parents=True)
    (out / loaded.forecasts_file).write_text(json.dumps(FORECASTS), encoding="utf-8")
    (out / loaded.evaluation_file).write_text(json.dumps(EVALUATION), encoding="utf-8")
    return loaded


NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)  # 07:00 en Cali, 7 h después de la emisión


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_now] = lambda: NOW
    with TestClient(app) as test_client:
        yield test_client


def test_forecast_returns_latest_operational_forecast_matching_contract(client: TestClient) -> None:
    response = client.get("/forecast")
    assert response.status_code == 200
    body = response.json()
    assert_matches(body, "Forecast")
    assert (body["target_date"], body["variant"], body["replay"]) == (
        "2026-10-23",
        "operativa",
        False,
    )
    assert body["stale"] is False
    assert body["explanation"] is None
    assert body["explanation_fallback"] is False
    assert body["threshold_mm"] == 20.0
    assert body["data_plan"] == "plan_b_earthdata"


def test_disclaimer_and_official_link_are_always_present(client: TestClient) -> None:
    for query in ("", "?replay_date=2024-12-31", "?replay_date=2024-12-31&variant=operativa"):
        body = client.get(f"/forecast{query}").json()
        assert body["disclaimer"].startswith(DISCLAIMER)
        assert "No es una alerta oficial" in body["disclaimer"]
        assert body["official_channels_url"] == OFFICIAL
        assert OFFICIAL in body["disclaimer"]  # canal principal
        assert IDEAM in body["disclaimer"]  # segundo canal: pronósticos y alertas del IDEAM


def test_replay_defaults_to_the_operational_variant(client: TestClient) -> None:
    """Revisión visual del 2026-11-01: la reproducción muestra lo que se habría publicado."""
    body = client.get("/forecast", params={"replay_date": "2024-12-31"}).json()
    assert_matches(body, "Forecast")
    assert (body["variant"], body["replay"], body["prob_ge_threshold"]) == ("operativa", True, 0.11)


def test_replay_can_ask_for_the_historical_variant(client: TestClient) -> None:
    body = client.get("/forecast", params={"replay_date": "2024-12-31", "variant": "historica"})
    assert body.json()["prob_ge_threshold"] == 0.15


def test_forecast_carries_the_warning_threshold_and_risk_of_its_variant(
    client: TestClient,
) -> None:
    body = client.get("/forecast", params={"replay_date": "2024-12-31"}).json()
    assert (body["decision_threshold"], body["risk"]) == (0.11, "elevado")  # 0,11 ≥ 0,11
    other = client.get("/forecast", params={"replay_date": "2024-12-31", "variant": "historica"})
    assert (other.json()["decision_threshold"], other.json()["risk"]) == (None, None)


def test_without_daily_table_there_is_no_percentile_or_climatology(client: TestClient) -> None:
    body = client.get("/forecast", params={"replay_date": "2024-12-31"}).json()
    assert (body["accum_3d_percentile"], body["climatology_prob"]) == (None, None)


def test_percentile_and_climatology_come_from_the_training_period(
    client: TestClient, settings: Settings
) -> None:
    header = (
        "date,series_id,precip_mm,n_readings,valid,imputed,source_hash,n_suspect,suspect_mm,n_gap\n"
    )
    rows = [
        f"2014-01-{d:02d},EST-A,{25.0 if d % 5 == 0 else 10.0},144,true,false,h,0,0.0,0\n"
        for d in range(1, 31)
    ]
    rows.append("2024-12-31,EST-A,99.0,144,true,false,h,0,0.0,0\n")  # fuera del entrenamiento
    (settings.data_dir / settings.daily_stations_file).write_text(header + "".join(rows))
    body = client.get("/forecast", params={"replay_date": "2024-12-31"}).json()
    assert_matches(body, "Forecast")
    assert body["accum_3d_percentile"] == 100  # 50,4 mm > todos los acumulados de enero de 2014
    assert body["climatology_prob"] == pytest.approx(3 / 16)  # ±15 días: 1 al 16 de enero


def test_historical_variant_outside_replay_is_rejected(client: TestClient) -> None:
    response = client.get("/forecast", params={"variant": "historica"})
    assert response.status_code == 422
    assert_matches(response.json(), "Error")
    assert response.json()["code"] == "variante_no_disponible"


def test_invalid_query_returns_contract_error(client: TestClient) -> None:
    response = client.get("/forecast", params={"replay_date": "no-es-fecha"})
    assert response.status_code == 422
    assert_matches(response.json(), "Error")


def test_forecast_older_than_24h_is_stale(client: TestClient) -> None:
    client.app.dependency_overrides[get_now] = lambda: datetime(2026, 10, 25, tzinfo=UTC)  # type: ignore[attr-defined]
    assert client.get("/forecast").json()["stale"] is True


def test_replay_date_without_forecast_is_503(client: TestClient) -> None:
    response = client.get("/forecast", params={"replay_date": "2010-01-01"})
    assert response.status_code == 503
    assert_matches(response.json(), "Error")


def test_missing_forecast_artifact_is_503(client: TestClient, settings: Settings) -> None:
    (settings.data_dir / settings.forecasts_file).unlink()
    response = client.get("/forecast")
    assert response.status_code == 503
    assert response.json()["code"] == "sin_pronostico"


def test_evaluation_matches_contract(client: TestClient) -> None:
    response = client.get("/evaluation")
    assert response.status_code == 200
    assert_matches(response.json(), "EvaluationReport")
    assert response.json()["data_plan"] == "plan_b_earthdata"


def test_evaluation_for_a_rule_not_evaluated_is_422(client: TestClient) -> None:
    response = client.get("/evaluation", params={"target_rule": "any_station"})
    assert response.status_code == 422
    assert response.json()["code"] == "regla_no_evaluada"


def test_missing_evaluation_artifact_is_503(client: TestClient, settings: Settings) -> None:
    (settings.data_dir / settings.evaluation_file).unlink()
    response = client.get("/evaluation")
    assert response.status_code == 503
    assert_matches(response.json(), "Error")


@pytest.mark.parametrize(
    ("path", "params", "status"),
    [
        ("/forecast", {}, 200),
        ("/forecast", {"variant": "historica"}, 422),
        ("/forecast", {"replay_date": "2010-01-01"}, 503),
        ("/evaluation", {}, 200),
        ("/evaluation", {"target_rule": "any_station"}, 422),
    ],
)
def test_statuses_are_documented(
    client: TestClient, path: str, params: dict[str, str], status: int
) -> None:
    assert client.get(path, params=params).status_code == status
    assert status in documented_statuses(path)


def test_default_settings_dependency_reads_environment(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, env_file: Path
) -> None:
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    assert get_settings().official_channels_url == OFFICIAL
    get_settings.cache_clear()
    assert get_now().tzinfo is not None


@pytest.mark.parametrize("content", ["{no es json", '[{"variant": "operativa"}]'])
def test_corrupt_forecast_artifact_is_503_not_500(
    client: TestClient, settings: Settings, content: str
) -> None:
    (settings.data_dir / settings.forecasts_file).write_text(content, encoding="utf-8")
    response = client.get("/forecast")
    assert response.status_code == 503
    assert response.json()["code"] == "artefacto_invalido"


def test_corrupt_evaluation_artifact_is_503_not_500(client: TestClient, settings: Settings) -> None:
    (settings.data_dir / settings.evaluation_file).write_text('{"daily": 1}', encoding="utf-8")
    response = client.get("/evaluation")
    assert response.status_code == 503
    assert_matches(response.json(), "Error")


def test_verified_explanation_is_published_with_its_fallback_flag(client: TestClient) -> None:
    seen: list[Forecast] = []

    def explainer(forecast: Forecast) -> VerifiedExplanation:
        seen.append(forecast)
        return VerifiedExplanation(text="Explicación verificada.", fallback=True)

    client.app.dependency_overrides[get_explainer] = lambda: explainer  # type: ignore[attr-defined]
    body = client.get("/forecast", params={"replay_date": "2024-12-31"}).json()
    assert_matches(body, "Forecast")
    assert (body["explanation"], body["explanation_fallback"]) == ("Explicación verificada.", True)
    assert (seen[0].prob_ge_threshold, seen[0].risk) == (0.11, "elevado")  # con contexto


def test_explanation_that_does_not_pass_the_gate_is_null(client: TestClient) -> None:
    client.app.dependency_overrides[get_explainer] = lambda: lambda _: None  # type: ignore[attr-defined]
    body = client.get("/forecast").json()
    assert (body["explanation"], body["explanation_fallback"]) == (None, False)


def test_default_explainer_is_disabled_without_api_key_or_fallback(settings: Settings) -> None:
    assert settings.demo_fallback is False
    assert build_explainer(settings) is None


def test_default_explainer_is_enabled_with_demo_fallback(env_file: Path) -> None:
    rewrite_env(env_file, DEMO_FALLBACK="1")
    assert build_explainer(Settings(_env_file=env_file)) is not None


def test_disclaimer_without_official_url_still_names_the_ideam(env_file: Path) -> None:
    settings = Settings(_env_file=rewrite_env(env_file, OFFICIAL_CHANNELS_URL=""))
    text = disclaimer_text(settings)
    assert text.startswith(DISCLAIMER)
    assert IDEAM in text
    assert "()" not in text
