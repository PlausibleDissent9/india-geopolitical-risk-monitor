"""The design system, held to its own rules.

tokens.css is the single source of truth for palette, type scale,
spacing and motion. Two things about it are promises rather than
preferences, and promises get tests:

  * Contrast. The design brief requires WCAG AA minimum. --faint was
    first set to #626C7C, which is 3.59:1 -- AA-large only, and the
    token exists specifically to colour SMALL text (axis labels, fine
    print). Caught by measuring before anything used it.
  * One scale. The site had thirteen font sizes, several of them
    (11.52, 14.08, 12.48) the residue of nested em compounding rather
    than decisions. A literal font-size in either sheet means the ramp
    has a gap and someone routed around it.
"""
from __future__ import annotations

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1] / "docs"
TOKENS = DOCS / "tokens.css"


def _srgb(v: float) -> float:
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * _srgb(r) + 0.7152 * _srgb(g) + 0.0722 * _srgb(b)


def contrast(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _tokens(block: str) -> dict[str, str]:
    text = TOKENS.read_text(encoding="utf-8")
    start = text.index(block)
    end = text.index("}", start)
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})",
                           text[start:end]))


def test_dark_theme_text_meets_wcag_aa():
    t = _tokens(":root {")
    paper = t["paper"]
    for name, minimum in (("ink", 4.5), ("muted", 4.5), ("faint", 4.5),
                          ("accent", 4.5), ("link", 4.5)):
        r = contrast(t[name], paper)
        assert r >= minimum, (
            f"dark --{name} is {r:.2f}:1 on --paper, below AA ({minimum})")


def test_light_theme_text_meets_wcag_aa():
    t = _tokens(':root[data-theme="light"] {')
    paper = t["paper"]
    for name in ("ink", "muted", "faint", "accent", "link"):
        if name not in t:
            continue
        r = contrast(t[name], paper)
        assert r >= 4.5, (
            f"light --{name} is {r:.2f}:1 on --paper, below AA")


def test_channel_colours_are_distinguishable_without_colour():
    """Five series that differ only in hue are one legend for
    trichromats and no legend for everyone else. They must separate in
    luminance too, so the lines survive greyscale and the common colour
    vision deficiencies."""
    t = _tokens(":root {")
    chans = {k: v for k, v in t.items() if k.startswith("ch-")}
    assert len(chans) == 5, f"expected 5 channel colours, got {len(chans)}"
    lums = sorted(luminance(v) for v in chans.values())
    gaps = [b - a for a, b in zip(lums, lums[1:])]
    assert min(gaps) > 0.015, (
        "two channel colours sit at effectively the same luminance and "
        f"would merge in greyscale: gaps {[round(g, 4) for g in gaps]}")


def test_neither_stylesheet_hardcodes_a_font_size():
    """Every size names a ramp step. A literal here means the ramp has a
    gap and the next person will invent a fourteenth size."""
    offenders = []
    for sheet in ("site.css", "style.css"):
        text = (DOCS / sheet).read_text(encoding="utf-8")
        for m in re.finditer(r"font-size:\s*([0-9.]+)(rem|px)", text):
            offenders.append(f"{sheet}: {m.group(0)}")
    assert not offenders, f"hardcoded font sizes outside the scale: {offenders}"


def test_the_palette_is_declared_exactly_once():
    """Both sheets used to declare the same colours under a comment
    asking the next editor to keep them in step. That failed on
    2026-07-31 and greyed every chart on the analysis page."""
    for sheet in ("site.css", "style.css"):
        text = (DOCS / sheet).read_text(encoding="utf-8")
        assert 'tokens.css' in text, f"{sheet} does not import the tokens"
        # A raw hex in a :root block would be a second source of truth.
        roots = re.findall(r":root[^{]*\{([^}]*)\}", text)
        for body in roots:
            hexes = re.findall(r"#[0-9A-Fa-f]{6}", body)
            assert not hexes, (
                f"{sheet} declares raw colours in :root ({hexes}); the "
                "palette belongs in tokens.css only")


def test_reduced_motion_is_honoured():
    text = TOKENS.read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in text, (
        "tokens.css must zero its motion durations for anyone who asked "
        "their system for less motion")
