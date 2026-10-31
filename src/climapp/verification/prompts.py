"""Instrucciones de Muse Spark para cada tarea de la compuerta (ADR-002 §2).

Las instrucciones piden JSON sin texto alrededor. Ninguna cifra se le pide al modelo
que la calcule: las cifras se le entregan y la compuerta exige que las copie igual.
"""

import json
from collections.abc import Collection, Mapping, Sequence

from climapp.verification.checks import Reason
from climapp.verification.muse import Message

JUDGE_SYSTEM = (
    "Eres un juez estricto de un sistema de reportes de lluvia. Recibes afirmaciones y "
    "la evidencia disponible (texto del ciudadano y datos del sistema). Para cada "
    "afirmación decide si la evidencia la respalda de forma directa; si hay duda, "
    "supported=false. Responde SOLO con JSON, sin texto adicional ni bloques de código: "
    '{"claims": [{"text": <afirmación copiada tal cual>, "evidence": <cita breve de la '
    'evidencia o "ninguna">, "supported": true|false}]}, una entrada por afirmación y en '
    "el mismo orden."
)

STRUCTURE_SYSTEM = (
    "Conviertes el reporte de un ciudadano sobre lluvia en la cuenca del río Pance en un "
    "registro estructurado. No inventes nada que el ciudadano no diga. Responde SOLO con "
    "JSON, sin texto adicional ni bloques de código, con exactamente estos campos: "
    '"event_type" (lluvia | crecida | deslizamiento | granizo | sin_lluvia | otro), '
    '"intensity" (ninguna | debil | moderada | fuerte), "observed_at" (ISO 8601 con zona; '
    'si el ciudadano no da la hora, usa la hora de recepción), "claims" (lista de '
    'afirmaciones atómicas y verificables tomadas del reporte) y "numbers_cited" (lista '
    "vacía: el reporte no cita cifras del sistema)."
)

EXPLAIN_SYSTEM = (
    "Explicas en español sencillo, en máximo 600 caracteres, un pronóstico experimental "
    "de lluvia para mañana en la cuenca del río Pance. No es una alerta oficial y no lo "
    "presentes como tal; nunca digas que es seguro ir al río. Habla solo de lluvia: no "
    "hables de crecientes, inundaciones ni alertas. Escribe la probabilidad con el "
    "símbolo % pegado a su cifra con un espacio (por ejemplo, «N %»). Usa SOLO las cifras que se "
    "te entregan, copiadas exactamente; cualquier otra cantidad escríbela en palabras y "
    "no escribas fechas con números. Responde SOLO con JSON, sin texto adicional ni "
    'bloques de código: {"text": <explicación>, "numbers_cited": [<cada cifra que '
    "aparece en el texto>]}."
)


def judge_messages(claims: Sequence[str], evidence: str) -> list[Message]:
    """Mensajes del juez para unas afirmaciones y su evidencia."""
    payload = {"afirmaciones": list(claims), "evidencia": evidence}
    return [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def feedback_message(reasons: Collection[Reason]) -> Message:
    """Mensaje que le pasa al siguiente intento los motivos del rechazo anterior."""
    listed = ", ".join(r.value for r in reasons)
    return {
        "role": "user",
        "content": f"Tu respuesta anterior fue rechazada por: {listed}. Corrígela y "
        "responde de nuevo siguiendo las instrucciones al pie de la letra.",
    }


def structure_messages(text: str, received_at: str) -> list[Message]:
    """Mensajes para estructurar un reporte ciudadano."""
    user = json.dumps({"reporte": text, "hora_de_recepcion": received_at}, ensure_ascii=False)
    return [{"role": "system", "content": STRUCTURE_SYSTEM}, {"role": "user", "content": user}]


def explain_messages(figures: Mapping[str, object]) -> list[Message]:
    """Mensajes para explicar un pronóstico a partir de sus cifras y su significado."""
    user = json.dumps({"pronostico": dict(figures)}, ensure_ascii=False)
    return [{"role": "system", "content": EXPLAIN_SYSTEM}, {"role": "user", "content": user}]
