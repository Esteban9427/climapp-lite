"""Los colores de `tokens.css` cumplen WCAG 2.1 AA (docs/design.md, TASK-017)."""

import re
from pathlib import Path

import pytest

TOKENS = Path(__file__).resolve().parents[2] / "src/climapp/web/static/tokens.css"
TEXT, NON_TEXT = 4.5, 3.0

PAIRS = [
    ("--color-text", "--color-bg", TEXT),
    ("--color-text", "--color-surface", TEXT),
    ("--color-text-muted", "--color-bg", TEXT),
    ("--color-text-muted", "--color-surface", TEXT),
    ("--color-on-primary", "--color-primary", TEXT),
    ("--color-primary", "--color-bg", TEXT),
    ("--color-warning-text", "--color-warning-bg", TEXT),
    ("--color-warning-border", "--color-bg", NON_TEXT),
    ("--color-info-text", "--color-info-bg", TEXT),
    ("--color-success-text", "--color-success-bg", TEXT),
    ("--color-danger-text", "--color-danger-bg", TEXT),
    ("--color-review-text", "--color-review-bg", TEXT),
    ("--color-disabled-text", "--color-disabled-bg", TEXT),
    ("--color-border", "--color-bg", NON_TEXT),
    ("--color-replay-text", "--color-replay-bg", TEXT),
]


def _tokens() -> dict[str, str]:
    css = TOKENS.read_text(encoding="utf-8")
    return dict(re.findall(r"(--color-[a-z-]+):\s*(#[0-9A-Fa-f]{6})", css))


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize(("fg", "bg", "minimum"), PAIRS)
def test_pair_meets_wcag_aa(fg: str, bg: str, minimum: float) -> None:
    tokens = _tokens()
    assert contrast(tokens[fg], tokens[bg]) >= minimum


def test_design_doc_lists_the_same_colors_as_the_css() -> None:
    doc = (TOKENS.parents[4] / "docs/design.md").read_text(encoding="utf-8")
    for name, value in _tokens().items():
        assert value.upper() in doc.upper(), name
