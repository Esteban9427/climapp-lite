"""Verificación de un reporte ciudadano: compuerta y confianza (ADR-002, TASK-016).

Un reporte con texto pasa por la compuerta (estructurar → deterministas → juez →
reintentos). Si se verifica, la confianza la calcula código con la evidencia disponible.
Una foto sin texto va a revisión humana: v1 no verifica imágenes con el modelo.
"""

from collections.abc import Sequence
from dataclasses import asdict, dataclass

from climapp.api.schemas import ReportRecord, VerificationAttemptOut
from climapp.logging import get_logger
from climapp.verification.confidence import ConfidenceWeights, compute_confidence
from climapp.verification.evidence import EvidenceSources
from climapp.verification.gate import GateRequest, GateResult, run_gate
from climapp.verification.muse import MuseClient, MuseError, MuseTask
from climapp.verification.prompts import structure_messages
from climapp.verification.schemas import ReportStructured

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ReportVerifier:
    """Todo lo que hace falta para verificar un reporte."""

    client: MuseClient
    sources: EvidenceSources
    groups: Sequence[Sequence[str]]
    weights: ConfidenceWeights
    max_attempts: int

    def _gate(self, record: ReportRecord, text: str) -> GateResult[ReportStructured]:
        """Corre la compuerta sobre el texto del ciudadano."""
        request = GateRequest(
            task=MuseTask.STRUCTURE,
            schema=ReportStructured,
            messages=structure_messages(text, record.received_at.isoformat()),
            allowed_numbers=frozenset(),
            evidence=f"Texto del ciudadano: {text}",
        )
        return run_gate(self.client, request, self.max_attempts)

    def verify(self, record: ReportRecord) -> ReportRecord:
        """Reporte con su estado final, intentos, registro y confianza."""
        if not record.text:
            log.info("report.photo_only", report_id=str(record.id))
            return record.model_copy(update={"status": "requiere_revision_humana"})
        try:
            result = self._gate(record, record.text)
        except MuseError as err:
            log.warning("report.muse_error", report_id=str(record.id), error=str(err))
            return record.model_copy(update={"status": "requiere_revision_humana"})
        attempts = [VerificationAttemptOut(**asdict(a)) for a in result.attempts]
        update: dict[str, object] = {
            "status": result.status,
            "attempts": attempts,
            "fallback": result.fallback,
        }
        if result.output is not None:
            evidence = self.sources.evidence_for(result.output)
            update |= {
                "structured": result.output,
                "confidence": compute_confidence(evidence, self.groups, self.weights),
            }
        log.info(
            "report.verified",
            report_id=str(record.id),
            status=result.status,
            attempts=len(attempts),
        )
        return record.model_copy(update=update)
