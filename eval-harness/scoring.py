"""Puntuación del set de evaluación de reportes (TASK-021 paso 3, TASK-036).

Funciones puras sobre los resultados de `run_eval.py`. La regla de acierto es la de
`eval-harness/README.md`: ningún modelo la decide.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from statistics import median, quantiles

Result = Mapping[str, object]
CATEGORIES = ("coincide", "parcial", "no_coincide", "revision_humana")
HITS = {
    "verdadero": frozenset({"coincide"}),
    "exagerado": frozenset({"revision_humana"}),
    "falso": frozenset({"revision_humana", "no_coincide"}),
}
P95_CUTS = 20  # quantiles(n=20)[18] es el percentil 95


@dataclass(frozen=True, slots=True)
class Bands:
    """Bandas de la etiqueta visible (`AGREEMENT_HIGH`, `AGREEMENT_LOW`, ADR-002 §4)."""

    high: float
    low: float


@dataclass(frozen=True, slots=True)
class Prices:
    """Precios de Muse Spark en US$ por millón de tokens (ADR-002, verificados 2026-10-29)."""

    input_per_m: float
    output_per_m: float


def category(status: str, score: float | None, bands: Bands) -> str:
    """Categoría obtenida: revisión humana o la banda de confianza de un verificado.

    Args:
        status: estado final de la compuerta.
        score: confianza (`None` si no se verificó).
        bands: bandas de la etiqueta visible.

    Returns:
        Una de `CATEGORIES`.
    """
    if status != "verificado" or score is None:
        return "revision_humana"
    if score >= bands.high:
        return "coincide"
    return "parcial" if score >= bands.low else "no_coincide"


def is_hit(label: str, cat: str) -> bool:
    """Indica si la categoría obtenida es un acierto para la etiqueta esperada.

    Raises:
        KeyError: si la etiqueta no existe.
    """
    return cat in HITS[label]


def _attempts(result: Result) -> Sequence[Mapping[str, object]]:
    """Intentos registrados del resultado."""
    attempts = result.get("attempts")
    return attempts if isinstance(attempts, list) else []


def first_attempt_category(result: Result, bands: Bands) -> str:
    """Categoría que habría dado la compuerta con un solo intento (pass@1).

    Si el primer intento pasó, la salida final es la de ese intento; si no, con un solo
    intento el reporte habría ido a revisión humana.
    """
    attempts = _attempts(result)
    if not attempts or not attempts[0]["passed"]:
        return "revision_humana"
    return final_category(result, bands)


def final_category(result: Result, bands: Bands) -> str:
    """Categoría final del resultado (dentro de `VERIFY_MAX_ATTEMPTS`)."""
    score = result.get("confidence")
    return category(str(result["status"]), score if isinstance(score, float | int) else None, bands)


def cost_usd(result: Result, prices: Prices) -> float:
    """Costo del reporte: tokens de todos sus intentos por los precios."""
    tokens_in = sum(int(str(a["tokens_in"])) for a in _attempts(result))
    tokens_out = sum(int(str(a["tokens_out"])) for a in _attempts(result))
    return (tokens_in * prices.input_per_m + tokens_out * prices.output_per_m) / 1e6


def latency_s(result: Result) -> float:
    """Latencia del reporte: suma de las latencias de sus intentos, en segundos."""
    return sum(int(str(a["latency_ms"])) for a in _attempts(result)) / 1000


def _p95(values: Sequence[float]) -> float:
    """Percentil 95 (con menos de 2 valores, el máximo)."""
    return max(values) if len(values) < 2 else quantiles(values, n=P95_CUTS)[18]  # noqa: PLR2004


def _rates(results: Sequence[Result], bands: Bands, prices: Prices) -> dict[str, float]:
    """Tasas, costo y latencia de un grupo de resultados."""
    n = len(results)
    finals = [final_category(r, bands) for r in results]
    firsts = [first_attempt_category(r, bands) for r in results]
    labels = [str(r["etiqueta_esperada"]) for r in results]
    latencies = [latency_s(r) for r in results]
    return {
        "n": n,
        "pass_at_1": sum(is_hit(lb, c) for lb, c in zip(labels, firsts, strict=True)) / n,
        "acierto_en_3": sum(is_hit(lb, c) for lb, c in zip(labels, finals, strict=True)) / n,
        "revision_humana": finals.count("revision_humana") / n,
        "intentos_medios": sum(len(_attempts(r)) for r in results) / n,
        "costo_usd": sum(cost_usd(r, prices) for r in results),
        "latencia_p50_s": median(latencies),
        "latencia_p95_s": _p95(latencies),
    }


def _grouped(results: Iterable[Result], key: str) -> dict[str, list[Result]]:
    """Resultados agrupados por el valor de `key`."""
    groups: dict[str, list[Result]] = {}
    for result in results:
        groups.setdefault(str(result[key]), []).append(result)
    return groups


def summarize(results: Sequence[Result], bands: Bands, prices: Prices) -> dict[str, dict]:  # type: ignore[type-arg]
    """Resumen: total, por etiqueta, por clase y matriz esperada vs. obtenida.

    Args:
        results: resultados de una corrida.
        bands: bandas de la etiqueta visible.
        prices: precios por millón de tokens.

    Returns:
        `{"total", "por_etiqueta", "por_clase", "matriz"}`.
    """
    by_label = _grouped(results, "etiqueta_esperada")
    matrix = {
        label: {c: [final_category(r, bands) for r in rows].count(c) for c in CATEGORIES}
        for label, rows in by_label.items()
    }
    return {
        "total": _rates(results, bands, prices),
        "por_etiqueta": {k: _rates(v, bands, prices) for k, v in by_label.items()},
        "por_clase": {k: _rates(v, bands, prices) for k, v in _grouped(results, "clase").items()},
        "matriz": matrix,
    }


def estimate_usd(observed_usd: float, runs: int, factor: float) -> float:
    """Costo estimado de `runs` corridas a partir del costo observado de una.

    Args:
        observed_usd: costo de la corrida de referencia.
        runs: corridas a estimar.
        factor: multiplicador por el esfuerzo mayor (SUPUESTO, se declara al usarlo).

    Returns:
        US$ estimados.
    """
    return observed_usd * runs * factor
