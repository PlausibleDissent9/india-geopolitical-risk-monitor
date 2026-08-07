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


def _strip_comments(css: str) -> str:
    """Scan declarations, not prose. The first version of the duplicate-
    keyframe check below reported `igrm-drift` twice -- once from the
    real rule and once from a comment ABOUT the real rule."""
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def test_motion_uses_the_scale_not_literals():
    """15 distinct durations across 46 literals (60, 80, 120, 140, 150,
    160, 180, 220, 240, 300, 400, 420, 500, 550, 600ms) is the
    font-size problem in the time dimension: a set of numbers that
    happened rather than a set that was chosen.

    THE FIRST VERSION OF THIS TEST MATCHED ONLY `\\d+ms`, so it could not
    see 36s, 28s or 3.2s -- three more durations, sitting in `animation:`
    shorthands, while DESIGN_SYSTEM.md said "Now four, enforced by a
    test." The test was the evidence for a claim it was not capable of
    checking. Seconds are matched now.
    """
    offenders = []
    for sheet in ("site.css", "style.css"):
        text = _strip_comments((DOCS / sheet).read_text(encoding="utf-8"))
        for m in re.finditer(r"(?<![\w.-])(\d+(?:\.\d+)?)(ms|s)(?![\w-])", text):
            offenders.append(f"{sheet}: {m.group(0)}")
    assert not offenders, (
        f"literal durations outside the scale: {offenders}. Name one of "
        "--dur-instant/quick/calm/slow/ambient, or add a step to the ramp.")


def test_one_easing_with_two_named_exceptions():
    """DESIGN_SYSTEM.md said "One easing." The sheets held FOUR, across
    33 declarations: 27 bare `ease`, 3 `ease-in-out`, 2 `linear`, and
    var(--ease) in a handful of places. Bare `ease` is
    cubic-bezier(0.25, 0.1, 0.25, 1) -- a different curve from the token,
    applied to most of the site, entirely by default.

    Two exceptions are legitimate and are TOKENS so they can be counted:
    --ease-linear for the reading-progress bar (an eased progress
    indicator reports a position the reader is not at) and --ease-loop
    for the one infinite alternating background drift (an asymmetric
    curve snaps at each turnaround). A third exception has to be argued
    for here rather than added quietly to a rule.
    """
    allowed = {"var(--ease)", "var(--ease-linear)", "var(--ease-loop)"}
    literal = re.compile(
        r"(?<![\w-])(ease-in-out|ease-out|ease-in|ease|linear|"
        r"cubic-bezier\([^)]*\)|step-(?:start|end)|steps\([^)]*\))(?![\w-])")
    offenders = []
    for sheet in ("site.css", "style.css"):
        text = _strip_comments((DOCS / sheet).read_text(encoding="utf-8"))
        # linear-gradient(...) is a paint function, not a timing function.
        text = re.sub(r"(?:repeating-)?(?:linear|radial|conic)-gradient", "", text)
        for m in literal.finditer(text):
            if m.group(0) not in allowed:
                offenders.append(f"{sheet}: {m.group(0)}")
    assert not offenders, (
        f"easing literals outside the token set: {offenders}. Use "
        f"var(--ease); the only other options are {sorted(allowed)} and "
        "each has a written reason in tokens.css.")


def test_reduced_motion_zeroes_every_duration_in_the_scale():
    """--dur-slow was declared in the ramp and NOT zeroed here for a day.

    It went unnoticed because the `*` catch-all sets
    transition-duration/animation-duration to 0.01ms !important, so the
    visible behaviour was correct -- by accident. A rule that works by
    accident is indistinguishable from one that works on purpose right
    up until the accident stops. So this compares the two lists directly
    instead of trusting that anyone remembered.
    """
    text = TOKENS.read_text(encoding="utf-8")
    root = text.split(":root {", 1)[1].split("\n}", 1)[0]
    declared = set(re.findall(r"(--dur-[\w-]+):", root))

    idx = text.find("@media (prefers-reduced-motion: reduce)")
    assert idx != -1, "the reduced-motion block is gone from tokens.css"
    block = text[idx:]
    zeroed = {name for name, val in
              re.findall(r"(--dur-[\w-]+):\s*(0m?s)", block)}

    missing = declared - zeroed
    assert not missing, (
        f"these durations are in the scale but are not zeroed for "
        f"prefers-reduced-motion: {sorted(missing)}. The catch-all below "
        "may hide it today; that is not the same as honouring the "
        "setting.")

    for prop in ("animation-delay", "transition-delay"):
        assert prop in block, (
            f"{prop} is not zeroed. A staggered reveal with its duration "
            "zeroed still waits its turn, so the page assembles itself in "
            "silence rather than simply being present.")


def test_keyframes_are_defined_exactly_once():
    """igrm-drift and igrm-pagein were each defined TWICE, once per
    sheet, under no comment at all -- the two-copies-of-the-palette
    failure that broke the gap chart on 2026-07-31, moved into the time
    dimension. Edit the homepage's copy and the other nineteen pages
    keep the old one, silently. Both sheets import tokens.css, so a
    keyframe belongs there and nowhere else.
    """
    seen: dict[str, list[str]] = {}
    for sheet in ("site.css", "style.css", "tokens.css"):
        text = _strip_comments((DOCS / sheet).read_text(encoding="utf-8"))
        for name in re.findall(r"@keyframes\s+([\w-]+)", text):
            seen.setdefault(name, []).append(sheet)

    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    assert not dupes, f"keyframes defined more than once: {dupes}"

    stray = {k: v for k, v in seen.items() if v != ["tokens.css"]}
    assert not stray, (
        f"keyframes outside tokens.css: {stray}. Both sheets import "
        "tokens.css; defining one in a sheet makes it available to half "
        "the site and invites a second copy for the other half.")


def test_only_the_background_field_animates_forever():
    """An instrument whose reading pulses is not calm.

    `.band-tick` -- the marker showing where today's value sits between
    calm and severe -- carried `tickpulse 3.2s infinite`: a permanent
    glow on the data itself, and on a phone a compositor job with no
    end. Motion attached to a number should report a finding, and "still
    here" is not one. It now arrives once and stops.

    The one permitted infinite animation is the background field at
    z-index -1, which carries no information at all.
    """
    offenders = []
    for sheet in ("site.css", "style.css"):
        text = _strip_comments((DOCS / sheet).read_text(encoding="utf-8"))
        for m in re.finditer(r"[^;{}]*animation:[^;}]*infinite[^;}]*", text):
            decl = " ".join(m.group(0).split())
            if "igrm-drift" not in decl:
                offenders.append(f"{sheet}: {decl}")
    assert not offenders, (
        f"infinite animations outside the background field: {offenders}")


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
