"""Tests de `climapp.config.Settings` (TASK-001)."""

from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from climapp.config import Settings
from tests.conftest import env_example_items, rewrite_env


def test_every_env_example_key_is_a_setting_and_vice_versa() -> None:
    fields = {name.upper() for name in Settings.model_fields}
    assert fields == set(env_example_items())


def test_loads_typed_values_from_env_file(env_file: Path) -> None:
    settings = Settings(_env_file=env_file)
    assert settings.muse_model == "muse-spark-1.3"
    assert settings.forecast_threshold_mm == 20.0
    assert settings.data_plan == "plan_b_earthdata"
    assert settings.demo_fallback is False
    assert settings.scope_freeze_date == date(2026, 11, 2)
    assert settings.data_dir == env_file.parent / "data"


def test_secrets_are_not_shown_in_repr(env_file: Path) -> None:
    rewrite_env(env_file, META_API_KEY="sk-no-mostrar")
    settings = Settings(_env_file=env_file)
    assert "sk-no-mostrar" not in repr(settings)
    assert settings.meta_api_key.get_secret_value() == "sk-no-mostrar"


@pytest.mark.parametrize("key", sorted(env_example_items()))
def test_missing_key_is_rejected_no_hidden_defaults(env_file: Path, key: str) -> None:
    rewrite_env(env_file, **{key: None})
    with pytest.raises(ValidationError):
        Settings(_env_file=env_file)


def test_empty_data_dir_is_rejected(env_file: Path) -> None:
    rewrite_env(env_file, DATA_DIR="")
    with pytest.raises(ValidationError, match="DATA_DIR"):
        Settings(_env_file=env_file)


def test_max_tokens_below_2000_is_rejected(env_file: Path) -> None:
    rewrite_env(env_file, MUSE_MAX_TOKENS="1999")
    with pytest.raises(ValidationError):
        Settings(_env_file=env_file)


@pytest.mark.parametrize(
    ("key", "value"),
    [("DATA_PLAN", "otro"), ("TARGET_RULE", "max"), ("STATION_GROUP_MIN_R", "1.5")],
)
def test_out_of_domain_values_are_rejected(env_file: Path, key: str, value: str) -> None:
    rewrite_env(env_file, **{key: value})
    with pytest.raises(ValidationError):
        Settings(_env_file=env_file)
