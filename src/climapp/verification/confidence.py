"""Confianza de un reporte, calculada por código y nunca por el LLM (ADR-002 §4).

Función pura y determinista. Fuentes: cada grupo de estaciones correlacionadas (una
estación sin pareja es su propio grupo), IMERG Early en la celda del reporte y el
pronóstico vigente. Un grupo indica lluvia si alguna de sus estaciones con dato
llegó a `RAIN_DAY_MM`. Cada fuente "concuerda" si su señal de lluvia coincide con lo que
dice el reporte; el puntaje es la suma de pesos de las que concuerdan sobre la suma de
pesos de las que tienen dato. Pesos: SUPUESTO fijos en configuración (TASK-021 los
calibra).

Si el reporte afirma una creciente, la subida de nivel del río en 24 h (TASK-039) es una
fuente más, aparte de la lluvia: concuerda si llegó a `LEVEL_RISE_THRESHOLD_M`. Sin dato
de nivel ese día, o en un reporte que no afirma creciente, no aporta nada.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from climapp.config import Settings

SourceKind = Literal["station_group", "satellite", "forecast", "river_level"]
SATELLITE_ID = "IMERG_E"
FORECAST_ID = "pronostico"
LEVEL_ID = "nivel"


@dataclass(frozen=True, slots=True)
class ConfidenceWeights:
    """Pesos por tipo de fuente y umbral de lluvia.

    Attributes:
        station: peso de cada grupo de estaciones (`CONFIDENCE_WEIGHT_STATION`, SUPUESTO,
            reducido porque r entre 0,49 y 0,75 sigue siendo dependencia).
        satellite: peso de IMERG Early (`CONFIDENCE_WEIGHT_SATELLITE`, SUPUESTO).
        forecast: peso del pronóstico vigente (`CONFIDENCE_WEIGHT_FORECAST`, SUPUESTO).
        rain_mm: lluvia mínima para "llovió" (`RAIN_DAY_MM`, 1 mm [OMM]).
        level: peso de la subida de nivel en reportes de creciente
            (`CONFIDENCE_WEIGHT_LEVEL`, SUPUESTO para JM, PRD SP-17).
        level_rise_m: subida mínima en 24 h para "hubo creciente"
            (`LEVEL_RISE_THRESHOLD_M`, SUPUESTO para JM, PRD SP-17).
    """

    station: float
    satellite: float
    forecast: float
    rain_mm: float
    level: float
    level_rise_m: float

    @classmethod
    def from_settings(cls, settings: Settings) -> "ConfidenceWeights":
        """Toma `CONFIDENCE_WEIGHT_*`, `RAIN_DAY_MM` y `LEVEL_RISE_THRESHOLD_M`."""
        return cls(
            station=settings.confidence_weight_station,
            satellite=settings.confidence_weight_satellite,
            forecast=settings.confidence_weight_forecast,
            rain_mm=settings.rain_day_mm,
            level=settings.confidence_weight_level,
            level_rise_m=settings.level_rise_threshold_m,
        )


@dataclass(frozen=True, slots=True)
class Evidence:
    """Evidencia disponible para un reporte.

    Attributes:
        report_rain: `True` si el reporte dice que llueve.
        station_mm: lluvia observada por estación en la ventana del reporte.
        satellite_mm: lluvia de IMERG Early en la celda; `None` si no hay dato.
        forecast_prob: probabilidad del pronóstico vigente; `None` si no hay.
        forecast_threshold: umbral de decisión del pronóstico (fijado fuera de la prueba).
        report_flood: `True` si el reporte afirma una creciente.
        level_rise_m: subida máxima de nivel en 24 h del día; `None` si no hay dato.
    """

    report_rain: bool
    station_mm: Mapping[str, float]
    satellite_mm: float | None
    forecast_prob: float | None
    forecast_threshold: float
    report_flood: bool = False
    level_rise_m: float | None = None


class ConfidenceSource(BaseModel):
    """Una fuente del desglose (`docs/data-model.md`)."""

    model_config = ConfigDict(frozen=True)

    source_id: str
    kind: SourceKind
    members: list[str]
    agrees: bool
    weight: float = Field(ge=0)


class Confidence(BaseModel):
    """Puntaje con su desglose; `independent_sources` cuenta grupos, no estaciones."""

    model_config = ConfigDict(frozen=True)

    score: float = Field(ge=0, le=1)
    sources: list[ConfidenceSource]
    independent_sources: int = Field(ge=0)


def _station_sources(
    evidence: Evidence, groups: Sequence[Sequence[str]], weights: ConfidenceWeights
) -> list[ConfidenceSource]:
    """Una fuente por grupo con dato: llovió si algún miembro con dato llegó a `rain_mm`.

    "Algún miembro" no cambia al agregar una copia de una estación (la media sí):
    así, duplicar una estación correlacionada nunca sube la confianza.
    """
    known = {s for g in groups for s in g}
    loose = [(s,) for s in sorted(evidence.station_mm) if s not in known]
    sources = []
    for group in [*(tuple(sorted(g)) for g in groups), *loose]:
        values = [evidence.station_mm[s] for s in group if s in evidence.station_mm]
        if values:
            rained = max(values) >= weights.rain_mm
            sources.append(
                ConfidenceSource(
                    source_id="+".join(group),
                    kind="station_group",
                    members=list(group),
                    agrees=rained == evidence.report_rain,
                    weight=weights.station,
                )
            )
    return sources


def _other_sources(evidence: Evidence, weights: ConfidenceWeights) -> list[ConfidenceSource]:
    """IMERG Early y el pronóstico vigente, si tienen dato."""
    sources = []
    if evidence.satellite_mm is not None:
        rained = evidence.satellite_mm >= weights.rain_mm
        sources.append(
            ConfidenceSource(
                source_id=SATELLITE_ID,
                kind="satellite",
                members=[],
                agrees=rained == evidence.report_rain,
                weight=weights.satellite,
            )
        )
    if evidence.forecast_prob is not None:
        alert = evidence.forecast_prob >= evidence.forecast_threshold
        sources.append(
            ConfidenceSource(
                source_id=FORECAST_ID,
                kind="forecast",
                members=[],
                agrees=alert == evidence.report_rain,
                weight=weights.forecast,
            )
        )
    return sources


def _level_source(evidence: Evidence, weights: ConfidenceWeights) -> list[ConfidenceSource]:
    """Subida de nivel, solo si el reporte afirma creciente y hay dato ese día."""
    if not evidence.report_flood or evidence.level_rise_m is None:
        return []
    return [
        ConfidenceSource(
            source_id=LEVEL_ID,
            kind="river_level",
            members=[],
            agrees=evidence.level_rise_m >= weights.level_rise_m,
            weight=weights.level,
        )
    ]


def compute_confidence(
    evidence: Evidence, groups: Sequence[Sequence[str]], weights: ConfidenceWeights
) -> Confidence:
    """Confianza del reporte (función pura).

    Args:
        evidence: lo que dice el reporte y lo que dicen las fuentes.
        groups: grupos de estaciones correlacionadas (`STATION_GROUPS_FILE`).
        weights: pesos SUPUESTO y umbral de lluvia.

    Returns:
        Puntaje en [0, 1] con su desglose; 0 si ninguna fuente tiene dato.
    """
    sources = [
        *_station_sources(evidence, groups, weights),
        *_other_sources(evidence, weights),
        *_level_source(evidence, weights),
    ]
    total = sum(s.weight for s in sources)
    agreeing = sum(s.weight for s in sources if s.agrees)
    score = agreeing / total if total > 0 else 0.0
    return Confidence(score=score, sources=sources, independent_sources=len(sources))


def load_station_groups(path: Path) -> tuple[tuple[str, ...], ...]:
    """Lee los grupos que escribe `climapp-groups`.

    Raises:
        OSError: si el archivo no se puede leer.
        json.JSONDecodeError, KeyError: si el artefacto no tiene `groups`.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    return tuple(tuple(group) for group in data["groups"])
