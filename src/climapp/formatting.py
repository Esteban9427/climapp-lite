"""Formato numérico es-CO: coma decimal y sin ceros sobrantes (revisión del 2026-11-01).

Lo usan la web y las cifras que recibe Muse. La compuerta compara números, no texto:
"40,8" y 40.8 son la misma cifra (`climapp.verification.schemas.numbers_in`).
"""


def es_number(value: float, decimals: int = 1) -> str:
    """Cifra con coma decimal, redondeada a `decimals` y sin ",0" sobrante: 20, 93,7."""
    text = f"{value:.{decimals}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")
