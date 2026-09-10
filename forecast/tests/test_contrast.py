"""Colour contrast, checked as arithmetic rather than by eye.

The brief asks for visible keyboard focus and a legible page. Contrast is the part of that
which is easy to get wrong invisibly -- a tone that looks fine to the person choosing it can
be unreadable to someone else -- so it is asserted rather than assumed.

Thresholds are WCAG 2.1 AA: 4.5:1 for body text, 3:1 for large text and non-text indicators.
"""

from __future__ import annotations

import pytest
from tracker import render


def relative_luminance(hex_colour: str) -> float:
    channels = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    red, green, blue = linear
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(foreground: str, background: str) -> float:
    a, b = relative_luminance(foreground), relative_luminance(background)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def test_the_contrast_helper_matches_known_values():
    """Anchor the maths: black on white is exactly 21:1, and any colour on itself is 1:1."""
    assert contrast("#000000", "#ffffff") == pytest.approx(21.0, abs=1e-9)
    assert contrast("#ffffff", "#ffffff") == pytest.approx(1.0, abs=1e-9)


# Each tone is checked against the surface it is actually drawn on. The two faint tones exist
# precisely because no single value clears AA on both paper and the ink panel.
ON_PAPER = [
    ("body text", render.INK, 4.5),
    ("secondary text", render.INK_SOFT, 4.5),
    ("faint text", render.INK_FAINT, 4.5),
    ("affirmed mark", render.AFFIRMED, 4.5),
    ("refuted mark", render.REFUTED, 4.5),
    ("ochre rules and focus ring", render.OCHRE, 3.0),
]

ON_PANEL = [
    ("chart text", render.PAPER, 4.5),
    ("reference diagonal", render.OCHRE_BRIGHT, 3.0),
    ("chart faint text", render.PANEL_FAINT, 4.5),
]


@pytest.mark.parametrize("name,colour,minimum", ON_PAPER)
def test_paper_palette_meets_wcag_aa(name, colour, minimum):
    achieved = contrast(colour, render.PAPER)
    assert achieved >= minimum, f"{name}: {achieved:.2f}:1 on paper, needs {minimum}:1"


@pytest.mark.parametrize("name,colour,minimum", ON_PANEL)
def test_panel_palette_meets_wcag_aa(name, colour, minimum):
    achieved = contrast(colour, render.INK)
    assert achieved >= minimum, f"{name}: {achieved:.2f}:1 on the ink panel, needs {minimum}:1"


def test_the_outcome_colours_differ_in_lightness_not_only_hue():
    """Hue alone fails a red-green colour-blind reader.

    These two started within 1.10:1 of each other, which is near-identical lightness: strip the
    hue and they were the same grey. The refuted tone is now darker so the pair survives being
    seen without colour at all.
    """
    assert contrast(render.AFFIRMED, render.REFUTED) >= 1.4


def test_outcome_is_never_carried_by_colour_alone():
    """Every outcome mark pairs its colour with a word and a glyph, for colour-blind readers."""
    from helpers import make

    html = render.build_page([make(80, True), make(80, False), make(50)], None, "unchecked")
    assert "affirmed" in html and "refuted" in html and "open" in html
    assert "&#9679;" in html and "&#9675;" in html   # filled and hollow glyphs
