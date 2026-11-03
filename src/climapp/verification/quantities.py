"""Cifras con unidad del texto del ciudadano (Fallo B, TASK-036).

Una cifra con unidad de longitud o de lluvia ("5 metros", "unos 60 centímetros",
"40 mm") que la estructuración no deja en `numbers_cited` se rechaza como `cifra_omitida`
(`checks.py`): si no, un reporte exagerado ("subió 5 metros") podía verificarse sin que
la cifra pasara por la compuerta. Todo se normaliza a metros, así que 5 m = 5 metros =
500 cm. Las horas ("4:10"), las fechas y las cifras sin unidad de medida no cuentan.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

METERS_PER_METER = 1.0
METERS_PER_CENTIMETER = 0.01
METERS_PER_MILLIMETER = 0.001
METERS_PER_UNIT: dict[str, float] = {
    "metros": METERS_PER_METER,
    "metro": METERS_PER_METER,
    "m": METERS_PER_METER,
    "centímetros": METERS_PER_CENTIMETER,
    "centimetros": METERS_PER_CENTIMETER,
    "centímetro": METERS_PER_CENTIMETER,
    "centimetro": METERS_PER_CENTIMETER,
    "cm": METERS_PER_CENTIMETER,
    "milímetros": METERS_PER_MILLIMETER,
    "milimetros": METERS_PER_MILLIMETER,
    "milímetro": METERS_PER_MILLIMETER,
    "milimetro": METERS_PER_MILLIMETER,
    "mm": METERS_PER_MILLIMETER,
}
RELATIVE_TOLERANCE = 1e-9  # las cifras se comparan ya convertidas: se exige igualdad
_UNITS = "|".join(sorted(METERS_PER_UNIT, key=len, reverse=True))
# Una cifra que no sigue a otra cifra, ":", "/", "-" ni separador decimal (horas y fechas),
# seguida de una unidad que termina la palabra ("10 min" no es "10 m")
QUANTITY = re.compile(
    rf"(?<![\d:/.,-])(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>{_UNITS})(?!\w)", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class Quantity:
    """Cifra con unidad, tal como se escribió y normalizada a metros."""

    value: float
    unit: str
    meters: float


def quantities_in(text: str) -> list[Quantity]:
    """Cifras con unidad de longitud o de lluvia escritas en el texto.

    Args:
        text: texto del ciudadano.

    Returns:
        Cada cifra con su unidad y su valor en metros, en orden de aparición.
    """
    found = []
    for match in QUANTITY.finditer(text):
        value = float(match["value"].replace(",", "."))
        unit = match["unit"].lower()
        found.append(Quantity(value, unit, value * METERS_PER_UNIT[unit]))
    return found


def _covers(cited: float, quantity: Quantity) -> bool:
    """`True` si la cifra citada, en alguna unidad conocida, es la misma cantidad."""
    tolerance = RELATIVE_TOLERANCE * max(abs(quantity.meters), 1.0)
    return any(
        abs(cited * factor - quantity.meters) <= tolerance for factor in METERS_PER_UNIT.values()
    )


def cited_covers(text: str, cited: Iterable[float]) -> bool:
    """`True` si cada cifra con unidad del texto está entre las cifras citadas.

    Args:
        text: texto del ciudadano.
        cited: `numbers_cited` de la estructuración.

    Returns:
        `False` si alguna cifra del texto quedó fuera de `numbers_cited`.
    """
    numbers = list(cited)
    return all(any(_covers(c, q) for c in numbers) for q in quantities_in(text))
