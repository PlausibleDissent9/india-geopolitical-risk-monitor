"""Value pins for the two frozen constants no test was watching.

The 2026-08-08 registration audit (analysis/registration_audit_2026-08-08.md)
found every signed registration structurally sound but two of them enforced
by nothing except git history:

  * the five production splice ratios (data/raw/ngram_calibration.json,
    frozen since a08fd02 per NOTES_FOR_ISHAN.md section 0.24, pending the
    founder's splice decision) -- and `python -m src.fetch_ngrams
    --calibrate` overwrites that file unconditionally, so a rerun would
    replace frozen constants with CI green;
  * the three frozen logit coefficients (validation/forecast_logit_frozen
    .json, registered 2026-08-06) -- the existing test checked only shape,
    so a silently edited coefficient passed.

Naming the values here means moving them requires editing two files and
explaining yourself in both. When the founder signs a new splice ratio or
a new forecast registration, this file changes IN THE SAME COMMIT, and the
message says which signed document authorizes it.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# NOTES_FOR_ISHAN.md section 0.24: production ratios frozen at their
# a08fd02 values until the founder decides the splice question. The
# audit's alternative ratios (2.4634/2.6998/1.8098) live in analysis
# artifacts only and must never appear here without a signed decision.
FROZEN_SPLICE = {
    "pakistan_west": {"ratio": 1.9547, "n_days": 5},
    "china_east": {"ratio": 3.3612, "n_days": 5},
    "gulf_energy": {"ratio": 1.791, "n_days": 5},
    "us_trade": {"ratio": 2.5616, "n_days": 1},
    "shipping": {"ratio": 2.9747, "n_days": 1},
}

# validation/forecast_registration.json, founder-signed 2026-08-06:
# fit once on pre-registration Mondays, then frozen. Refits are new
# registrations, never silent updates.
FROZEN_LOGIT = {
    "fit_date": "2026-08-06",
    "coefficients": [-0.645479, 0.003153, 0.008114],
    "n_obs": 2210,
    "base_rate": 0.3846,
    "train_mondays": ["2018-01-07", "2026-08-03"],
}


def test_the_production_splice_ratios_are_still_the_frozen_ones():
    cal = json.loads(
        (ROOT / "data" / "raw" / "ngram_calibration.json").read_text(
            encoding="utf-8"))
    assert set(cal) == set(FROZEN_SPLICE), (
        f"the calibration file's channel set changed: {sorted(cal)}")
    for ch, frozen in FROZEN_SPLICE.items():
        assert cal[ch]["ratio"] == frozen["ratio"], (
            f"{ch} production splice ratio moved from {frozen['ratio']} to "
            f"{cal[ch]['ratio']}. The ratios are frozen (NOTES 0.24) until "
            "the founder signs the splice decision; if that happened, this "
            "pin moves in the same commit citing the signature. If it did "
            "not, something ran --calibrate against a frozen instrument.")
        assert cal[ch]["n_days"] == frozen["n_days"], (
            f"{ch} calibration n_days changed; the overlap sample behind a "
            "frozen ratio cannot grow or shrink while the ratio is frozen")


def test_the_frozen_logit_is_still_the_registered_fit():
    frozen = json.loads(
        (ROOT / "validation" / "forecast_logit_frozen.json").read_text(
            encoding="utf-8"))
    for key, value in FROZEN_LOGIT.items():
        assert frozen[key] == value, (
            f"forecast_logit_frozen.json {key} is {frozen[key]!r}, "
            f"registered {value!r}. Refits are new registrations; a changed "
            "value here without a new signed registration is a silent refit.")


def test_a_regenerated_fit_cannot_wear_the_registered_date():
    """src/forecasts.py used to hardcode fit_date='2026-08-06' in the fit
    routine itself, so deleting the frozen file and rerunning would forge
    the original registration date onto post-registration data. The fit
    routine must not contain the registered date as a literal."""
    src = (ROOT / "src" / "forecasts.py").read_text(encoding="utf-8")
    assert '"fit_date": "2026-08-06"' not in src, (
        "the fit routine hardcodes the registered date; a regenerated "
        "fit would carry forged provenance")
