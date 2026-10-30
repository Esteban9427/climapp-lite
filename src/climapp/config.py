"""Configuración de ClimApp Lite leída de `.env` (sin valores por defecto ocultos).

Cada clave de `.env.example` es un campo obligatorio: si falta en el entorno o en
`.env`, `Settings()` falla. Los umbrales científicos están marcados SUPUESTO en
`docs/PRD.md` y en los ADR.
"""

from datetime import date
from pathlib import Path
from typing import Literal, Self
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Effort = Literal["low", "medium", "high"]
DataPlan = Literal["principal", "plan_b_earthdata", "plan_b_datos"]
TargetRule = Literal["any_station", "basin_mean", "reference_station"]

MIN_MUSE_MAX_TOKENS = 2000  # ADR-002: con menos tokens Muse corta la respuesta
READINGS_PER_DAY = 144  # una lectura del contador cada 10 min (ADR-004)


class Settings(BaseSettings):
    """Configuración tipada de la aplicación.

    Los nombres de campo corresponden, en mayúsculas, a las claves de `.env.example`.

    Raises:
        pydantic.ValidationError: si falta una clave o un valor está fuera de dominio.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

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

    local_timezone: ZoneInfo
    counter_sensors: list[str] = Field(min_length=1)
    max_step_mm: float = Field(gt=0)
    max_gap_min: int = Field(ge=1)
    suspect_step_mm: float = Field(gt=0)
    suspect_quiet_min: int = Field(ge=0)
    suspect_quiet_max_mm: float = Field(ge=0)

    station_exports: list[Path] = Field(min_length=1)
    station_map_file: Path
    daily_stations_file: Path
    min_readings: int = Field(ge=1, le=READINGS_PER_DAY)

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

    @model_validator(mode="after")
    def _suspect_below_max_step(self) -> Self:
        """Exige `SUSPECT_STEP_MM` < `MAX_STEP_MM`: un salto sobre el máximo ya es un pico."""
        if self.suspect_step_mm >= self.max_step_mm:
            msg = "SUSPECT_STEP_MM debe ser menor que MAX_STEP_MM (SP-12)"
            raise ValueError(msg)
        return self
