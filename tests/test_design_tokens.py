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
                          ("accent", 4.5)):
        if name not in t:
            continue
        r = contrast(t[name], paper)
        assert r >= minimum, (
            f"dark --{name} is {r:.2f}:1 on --paper, below AA ({minimum})")


def test_light_theme_text_meets_wcag_aa():
    t = _tokens(':root[data-theme="light"] {')
    paper = t["paper"]
    for name in ("ink", "muted", "faint", "accent"):
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


def test_the_phone_hero_rules_survive():
    """The brief: the headline number and the five channel rows ARE the
    hero and must read instantly on a phone. Measured at 375x812 before
    these rules existed, ZERO channel rows were visible without
    scrolling -- the instrument card started at y=563 and each row stood
    96px tall because a 90px sparkline squeezed the channel name onto
    three lines.

    These are the specific rules that bought it back (0 rows visible to
    3, row height 96px to 54px). A future edit that drops them should
    fail here rather than quietly restore a phone experience nobody
    checks.
    """
    css = (DOCS / "style.css").read_text(encoding="utf-8")
    idx = css.find("@media (max-width: 640px)")
    assert idx != -1, "the phone hero media query is gone"
    block = css[idx:]
    for rule, why in [
        (".component-row .spark", "the sparkline must be hidden on phones"),
        (".nowcast-channels", "the duplicate channel chips must be hidden"),
        (".mast-links", "the nav must scroll in one row, not wrap to three"),
    ]:
        assert rule in block, f"{rule} rule missing: {why}"


def test_responsive_overrides_come_last():
    """style.css declares .big-number three times. A media query placed
    before a later duplicate is silently undone -- which happened: the
    phone font-size was written, measured, and found to have no effect
    because a later rule re-declared it."""
    css = (DOCS / "style.css").read_text(encoding="utf-8")
    last_media = css.rfind("@media (max-width")
    assert last_media != -1
    tail = css[last_media:]
    stray = re.findall(r"^\.[\w-]+\s*\{", tail, re.M)
    assert not stray, (
        f"top-level rules appear after the responsive block ({stray}); "
        "they will override it")


def test_no_stylesheet_or_script_holds_a_third_palette_copy():
    """app.js carried seven hardcoded series hexes: a third copy of the
    palette after the two stylesheets, and the one that never followed
    the theme. Its composite colour was #12233D -- the LIGHT theme's ink
    -- so the composite line drew near-black on a near-black ground in
    the dark theme that ships by default."""
    js = (DOCS / "app.js").read_text(encoding="utf-8")
    body = js[:js.find("function seriesColor")] + js[js.find("const COLORS"):]
    hexes = re.findall(r'["\']#[0-9A-Fa-f]{6}["\']', body)
    assert not hexes, (
        f"app.js hardcodes colours ({hexes}); series colours belong in "
        "tokens.css so they follow the theme and stay testable")


def test_motion_uses_the_scale_not_literals():
    """15 distinct durations across 46 literals (60, 80, 120, 140, 150,
    160, 180, 220, 240, 300, 400, 420, 500, 550, 600ms) is the
    font-size problem in the time dimension: a set of numbers that
    happened rather than a set that was chosen."""
    offenders = []
    for sheet in ("site.css", "style.css"):
        text = (DOCS / sheet).read_text(encoding="utf-8")
        for m in re.finditer(r"(?<![\w.-])(\d+)ms(?![\w-])", text):
            offenders.append(f"{sheet}: {m.group(0)}")
    assert not offenders, f"literal durations outside the scale: {offenders}"


def test_no_easing_overshoots():
    """cubic-bezier(0.22, 1, 0.36, 1) rises past its target and settles
    back. On an instrument that reads as the number wobbling, which is
    the opposite of the brief's 'calm'."""
    bad = []
    for sheet in ("site.css", "style.css", "tokens.css"):
        text = (DOCS / sheet).read_text(encoding="utf-8")
        for m in re.finditer(r"cubic-bezier\(([^)]*)\)", text):
            pts = [float(x) for x in m.group(1).split(",")]
            # y1 (index 1) or y2 (index 3) above 1 means overshoot.
            if len(pts) == 4 and (pts[1] > 1.0 or pts[3] > 1.0):
                bad.append(f"{sheet}: {m.group(0)}")
    assert not bad, f"overshooting easings: {bad}"


def test_no_token_is_declared_and_never_used():
    """A token nobody references is not a system, it is a claim.

    Three shipped that way on 2026-08-07: a --sp-1..--sp-16 spacing
    ramp (deleted, spacing is deliberately not systematised), the motion
    durations (now applied to all 46 literals), and --link (deleted --
    applying it would have recoloured every link, which is a rebrand,
    and the brief says improve execution instead).
    """
    declared = set(re.findall(r"^\s*(--[\w-]+):", TOKENS.read_text(encoding="utf-8"),
                              re.M))
    used = ""
    for f in list(DOCS.glob("*.css")) + list(DOCS.glob("*.js")) + \
            list(DOCS.glob("*.html")):
        used += f.read_text(encoding="utf-8")
    dead = [t for t in sorted(declared)
            if f"var({t})" not in used
            and f'"{t}"' not in used and f"'{t}'" not in used]
    assert not dead, (
        f"tokens declared but never referenced: {dead}. Use them or "
        "delete them; a scale nobody applies is decoration.")
