# India Geopolitical Risk Monitor (IGRM)

[![ci](https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor/actions/workflows/ci.yml)
[![daily-update](https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor/actions/workflows/daily.yml/badge.svg)](https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor/actions/workflows/daily.yml)

A daily, category-decomposed index of geopolitical press salience for
India, with open data, a public methodology, and an event-study layer on
India-specific relative returns. IGRM measures attention, not the
probability or severity of geopolitical events, and is distinct from the
Caldara-Iacoviello GPR family. Live since July 2026.

**Built with AI assistance (Claude)**, pipeline, site, dictionaries, and
methodology. Weekly commentary is the author's. See `methodology.md`.

> **External precision status (2026-08-08):** blind-audit v2 was
> [invalidated before coding](validation/blind_audit_500/V2_INVALID.md) after
> a source-frame and estimand audit. No v2 labels or results exist, and no v3
> sample has been frozen. Prospective, label-free v3
> [source-frame collection](validation/precision_v3/PROTOCOL.md) begins with
> the 2026-08-08 score day; a day attestation is acquisition evidence, not a
> precision result. The published `precision.json` remains an explicitly
> uncalibrated machine/founder diagnostic, not an independent human result.

## Architecture

```
GDELT DOC API ──┐
                ├─> build_index.py ──> docs/data/{latest,history,episodes}
Yahoo Finance ──┘         │
                          └─> event_study.py ──> docs/data/event_study.json
GitHub Actions (daily 18:00 IST) commits outputs; GitHub Pages serves docs/
notes/*.md (author-written) ──> published to the site weekly
```

## Status

Live at https://plausibledissent9.github.io/india-geopolitical-risk-monitor/
with daily data since 2017-01-01, frozen v1.0.0 dictionaries, and a
pre-registered validation hit rate of **18/21 (86%)**. During the July
2026 DOC-API disruption the recent tail is computed from GDELT's Web
NGrams feed at the maintainer's direction, ratio-spliced on overlap days
(methodology changelog v1.0.1).

## Operations

- **Daily (automatic).** `daily-update` runs at 18:00 IST: the ngram
  bridge heals recent days, the pipeline rebuilds scores/episodes/event
  study, and outputs commit to `docs/`. It refuses to publish stale or
  partial data (fail-loud gate).
- **Validation.** `validate-and-analyze` (Actions) re-runs the full
  battery; hit-rate/seasonality/alt-specs are offline, the
  GDELT-dependent checks retry when the API allows.
- **Dictionaries are frozen.** Any change goes through the methodology
  changelog; CI enforces the ex-ante rule (no retrospective event names)
  and the query grammar across all term lists.
- **Weekly note.** Friday's run drops `notes-inbox/datapack_YYYY-Www.md`;
  write ~250 words to `notes/YYYY-Www.md` (the site footer's
  "write this week's note" link opens the editor), the next run
  publishes it to the site and RSS.

## Local run

The pipeline is pip-installable from a checkout (`pip install .`,
package name `igrm`; the import package stays `src` until the 1.0
restructure, and there is deliberately no PyPI upload — data files
live in the repository, so a checkout is the unit of reproduction).
For development:

```
pip install -r requirements.txt
pytest -q
python -m src.run_daily --backfill     # first time
python -m src.run_daily                # daily incremental
python -m src.make_datapack            # weekly note inputs
python -m src.validate hit-rate        # pre-registered episode detection
python -m src.validate placebo         # placebo channels (layer 4d)
python -m src.validate robustness      # broad/narrow dictionary variants
```

To verify the published numbers independently, see
[REPLICATION.md](REPLICATION.md) (a cached check takes ~5 minutes).
Decision rules, append-only surfaces, and the deprecation policy live
in [GOVERNANCE.md](GOVERNANCE.md); adding a country monitor follows
[countries/RECIPE.md](countries/RECIPE.md).

## Weekly rhythm

Friday's Action run drops `notes-inbox/datapack_YYYY-Www.md` (numbers
only). You write ~250 words, save as `notes/YYYY-Www.md`, commit. The next
daily run publishes it. That note is also the week's Indiconomics post.

## Roadmap, frozen until 1 Nov 2026

No new features before the application deadline; every feature-day is a
data-day lost. Post-freeze candidates: prediction extension (index
*changes* vs subsequent volatility changes, with controls, modest
framing), weighting exploration, per-episode case pages.

## Honest limitations

Association, not causation. Salience, not ground truth, anniversary
coverage counts by construction (disclosed in methodology §7). GDELT
reaches back to Jan 2017 only. Not investment advice.
