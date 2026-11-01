"""Cómo se ve un reporte: título, resultado con su por qué y desglose de evidencia.

Solo lee datos ya calculados (la confianza y los artefactos del día); no cambia la
confianza ni el contrato de la API. Revisión visual del 2026-11-01.
"""

from dataclasses import dataclass

from climapp.api.schemas import Report
from climapp.formatting import es_number
from climapp.verification.checks import Reason
from climapp.verification.confidence import Confidence, ConfidenceSource
from climapp.verification.evidence import DayValues
from climapp.web.agreement import AgreementThresholds, agreement_label

PERCENT = 100
EVENT_TEXT = {
    "lluvia": "Lluvia",
    "crecida": "Crecida",
    "deslizamiento": "Deslizamiento",
    "granizo": "Granizo",
    "sin_lluvia": "Sin lluvia",
    "otro": "Otro evento",
}
INTENSITY_TEXT = {"ninguna": "", "debil": "débil", "moderada": "moderada", "fuerte": "fuerte"}
REASON_TEXT = {
    Reason.AFIRMACION_SIN_EVIDENCIA: "el verificador no encontró respaldo en el texto para lo "
    "que se estructuró",
    Reason.RESPUESTA_VACIA: "el modelo no dio una respuesta completa",
    Reason.RESPUESTA_INCOMPLETA: "el modelo no dio una respuesta completa",
    Reason.ESQUEMA_INVALIDO: "la respuesta no tenía el formato esperado",
    Reason.CIFRA_NO_COINCIDE: "una cifra no coincidía con los datos",
    Reason.DATO_PERSONAL: "el texto parecía tener datos personales",
    Reason.HERRAMIENTA_NO_PERMITIDA: "el modelo pidió una herramienta no permitida",
}
REVIEW_TEXT = {
    "sin_grabacion": "Modo demo: este texto no tiene una respuesta grabada (sin grabación), "
    "así que no se verifica.",
    "muse_no_disponible": "El verificador no respondió.",
    "solo_foto": "Las fotos sin texto las revisa una persona.",
}


@dataclass(frozen=True, slots=True)
class ReportResult:
    """Resultado visible: titular, clase de la insignia y la frase de por qué."""

    headline: str
    css: str
    why: str


def event_title(event_type: str, intensity: str) -> str:
    """Tipo e intensidad con mayúscula inicial: "Crecida fuerte", "Sin lluvia"."""
    words = [EVENT_TEXT.get(event_type, event_type), INTENSITY_TEXT.get(intensity, intensity)]
    return " ".join(w for w in words if w)


def _support(confidence: Confidence) -> str:
    """Cuántas fuentes con dato respaldan el reporte."""
    total = len(confidence.sources)
    agree = sum(1 for s in confidence.sources if s.agrees)
    if not total:
        return "No hay fuentes con dato para ese día."
    if not agree:
        return f"Ninguna de las {total} fuentes con dato lo respalda."
    return f"Lo respaldan {agree} de {total} fuentes con dato."


def _review(report: Report) -> ReportResult:
    """Revisión humana: por la compuerta (tras sus intentos) o por otro motivo."""
    if report.review_reason is not None or not report.attempts:
        why = REVIEW_TEXT.get(report.review_reason or "", "Lo revisa una persona.")
        return ReportResult("En revisión humana", "badge-review", why)
    reasons = report.attempts[-1].reasons
    why = REASON_TEXT.get(reasons[0], reasons[0].value) if reasons else "sin motivo registrado"
    headline = f"En revisión humana (no pasó la verificación tras {len(report.attempts)} intentos)"
    return ReportResult(headline, "badge-review", f"Motivo del último intento: {why}.")


def report_result(report: Report, thresholds: AgreementThresholds) -> ReportResult | None:
    """Resultado de un reporte verificado o en revisión; `None` en los demás estados."""
    if report.status == "verificado" and report.confidence is not None:
        label = agreement_label(report.confidence.score, thresholds)
        return ReportResult(label.text, label.css, _support(report.confidence))
    if report.status == "requiere_revision_humana":
        return _review(report)
    return None


def _source_value(source: ConfidenceSource, values: DayValues) -> str:
    """Etiqueta y valor de una fuente, con el formato es-CO."""
    if source.kind == "station_group":
        members = [m for m in source.members if m in values.station_mm]
        mm = "; ".join(f"{m}: {es_number(values.station_mm[m])} mm" for m in members)
        return f"Lluvia en estaciones · {mm or 'sin dato'}"
    if source.kind == "satellite":
        mm = "sin dato" if values.satellite_mm is None else f"{es_number(values.satellite_mm)} mm"
        return f"Satélite IMERG Early · {mm}"
    if source.kind == "river_level":
        rise = "sin dato" if values.level_rise_m is None else es_number(values.level_rise_m, 2)
        return f"Nivel del río · subida de {rise} m en 24 h"
    prob = values.forecast_prob
    pct = "sin dato" if prob is None else f"{round(prob * PERCENT)} %"
    return f"Pronóstico del día · {pct}"


def evidence_rows(confidence: Confidence, values: DayValues) -> list[str]:
    """Una línea por fuente con su valor y ✓ si concuerda o ✗ si no."""
    return [f"{_source_value(s, values)} {'✓' if s.agrees else '✗'}" for s in confidence.sources]
