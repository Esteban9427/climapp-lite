"""Formato numérico es-CO para la UI y para las cifras que recibe Muse (2026-11-01)."""

import pytest

from climapp.formatting import es_number


@pytest.mark.parametrize(
    ("value", "text"),
    [(93.7, "93,7"), (20.0, "20"), (5.085, "5,1"), (0.0, "0"), (15, "15"), (40.84, "40,8")],
)
def test_comma_decimal_without_trailing_zero(value: float, text: str) -> None:
    assert es_number(value) == text


def test_decimals_can_be_chosen() -> None:
    assert es_number(0.68, decimals=2) == "0,68"
    assert es_number(1.0, decimals=2) == "1"
