"""Tests de las cifras con unidad del texto del ciudadano (Fallo B, TASK-036)."""

import pytest

from climapp.verification.quantities import cited_covers, quantities_in

FIVE_M = pytest.approx(5.0)


@pytest.mark.parametrize(
    ("text", "meters"),
    [
        ("el río subió 5 m", 5.0),
        ("subió 5 metros", 5.0),
        ("subió 500 cm", 5.0),
        ("subió un metro: 1 metro", 1.0),
        ("subió unos 60 centímetros", 0.6),
        ("subió unos 60 centimetros", 0.6),
        ("subió 1,5 metros", 1.5),
        ("subió 1.5 m", 1.5),
        ("cayeron 40 mm", 0.04),
        ("cayeron 40 milímetros", 0.04),
    ],
)
def test_quantities_are_normalized_to_meters(text: str, meters: float) -> None:
    (quantity,) = quantities_in(text)
    assert quantity.meters == pytest.approx(meters)


def test_five_meters_is_the_same_in_every_unit() -> None:
    values = [quantities_in(t)[0].meters for t in ("5 m", "5 metros", "500 cm", "5000 mm")]
    assert values == [FIVE_M] * 4


@pytest.mark.parametrize(
    "text",
    [
        "Reporte simulado: llueve duro arriba",
        "a las 4:10 el río estaba alto",
        "el 2024-05-14 llovió",
        "el 14/05 llovió",
        "llovió unas 3 horas",
        "el río viene café hace 10 min",
        "subió como medio metro",
    ],
)
def test_times_dates_prefix_and_bare_numbers_are_not_quantities(text: str) -> None:
    assert quantities_in(text) == []


@pytest.mark.parametrize(
    ("text", "cited", "covered"),
    [
        ("subió 5 metros", [5.0], True),
        ("subió 5 metros", [500.0], True),
        ("subió 5 metros", [], False),
        ("subió 5 metros", [6.0], False),
        ("subió unos 60 centímetros y cayeron 40 mm", [60.0], False),
        ("subió unos 60 centímetros y cayeron 40 mm", [60.0, 40.0], True),
        ("llueve duro arriba", [], True),
    ],
)
def test_cited_numbers_must_cover_every_quantity(
    text: str, cited: list[float], covered: bool
) -> None:
    assert cited_covers(text, cited) is covered
