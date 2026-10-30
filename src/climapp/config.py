"""Configuración de ClimApp Lite leída de `.env` (sin valores por defecto ocultos).

Cada clave de `.env.example` es un campo obligatorio: si falta en el entorno o en
`.env`, `Settings()` falla. Los umbrales científicos están marcados SUPUESTO en
`docs/PRD.md` y en los ADR.
"""

from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Effort = Literal["low", "medium", "high"]
DataPlan = Literal["principal", "plan_b_earthdata", "plan_b_datos"]
TargetRule = Literal["any_station", "basin_mean", "reference_station"]

MIN_MUSE_MAX_TOKENS = 2000  # ADR-002: con menos tokens Muse corta la respuesta


class Settings(BaseSettings):
    """Configuración tipada de la aplicación.

    Los nombres de campo corresponden, en mayúsculas, a las claves de `.env.example`.

    Raises:
        pydantic.ValidationError: si falta una clave o un valor está fuera de dominio.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    meta_api_key: SecretStr
    meta_api_base_url: str
    muse_model: str
    muse_effort_structure: Effort
    muse_effort_judge: Effort
    muse_max_tokens: int = Field(ge=MIN_MUSE_MAX_TOKENS)
    verify_max_attempts: int = Field(ge=1)

    data_dir: Path
    earthdata_token: SecretStr

    data_plan: DataPlan
    forecast_threshold_mm: float = Field(gt=0)
    accum3_threshold_mm: float = Field(gt=0)
    target_rule: TargetRule
    station_group_min_r: float = Field(ge=0, le=1)

    official_channels_url: str
    demo_fallback: bool
    scope_freeze_date: date

    @field_validator("data_dir", mode="before")
    @classmethod
    def _data_dir_not_empty(cls, value: object) -> object:
        """Rechaza `DATA_DIR` vacío, que se convertiría en el directorio actual."""
        if isinstance(value, str) and not value.strip():
            msg = "DATA_DIR no puede estar vacío: los datos viven fuera de git (ADR-004)"
            raise ValueError(msg)
        return value
