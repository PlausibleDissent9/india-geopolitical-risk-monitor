# India Geopolitical Risk Monitor (IGRM)

[![ci](https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor/actions/workflows/ci.yml)
[![daily-update](https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor/actions/workflows/daily.yml/badge.svg)](https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor/actions/workflows/daily.yml)

A daily, category-decomposed index of geopolitical risk salience for India,
in the Caldara–Iacoviello article-share tradition — with open data, a
public methodology, and an event-study layer on India-specific relative
returns. Live since July 2026.

**Built with AI assistance (Claude)** — pipeline, site, dictionaries, and
methodology. Weekly commentary is the author's. See `methodology.md`.

## Architecture

```
GDELT DOC API ──┐
                ├─> build_index.py ──> docs/data/{latest,history,episodes}
Yahoo Finance ──┘         │
                          └─> event_study.py ──> docs/data/event_study.json
GitHub Actions (daily 18:00 IST) commits outputs; GitHub Pages serves docs/
notes/*.md (author-written) ──> published to the site weekly
```

## Launch checklist

1. **Create the repo.** Public GitHub repo named
   `india-geopolitical-risk-monitor`. Push these contents. Replace the two
   `PlausibleDissent9` links in `docs/index.html` with your GitHub username.
2. **Enable Pages.** Settings → Pages → Deploy from branch → `main`,
   folder `/docs`.
3. **Review the dictionaries.** `dictionaries.json` is frozen (v1.0.0,
   2026-07-24) with a per-term rationale; any change you make goes in the
   methodology changelog. `pytest -q` enforces the ex-ante rule (no
   retrospective event names) and the GDELT query grammar in CI.
4. **First run.** Actions tab → `daily-update` → Run workflow →
   backfill = **true**. Expect 20–40 minutes (GDELT is chunked politely).
   The daily cron (18:00 IST) takes over afterwards.
5. **Validate.** After the backfill: `python -m src.validate hit-rate`
   scores the pre-registered episode list (the key figure), `placebo` and
   `robustness` run the layer-4 checks. Results land in
   `docs/data/validation.json`; report them in methodology §8.
6. **Verify.** Open the Pages URL. Composite number, five components,
   chart, archive should render. Then write the first weekly note.

## Local run

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

## Weekly rhythm

Friday's Action run drops `notes-inbox/datapack_YYYY-Www.md` (numbers
only). You write ~250 words, save as `notes/YYYY-Www.md`, commit. The next
daily run publishes it. That note is also the week's Indiconomics post.

## Roadmap — frozen until 1 Nov 2026

No new features before the application deadline; every feature-day is a
data-day lost. Post-freeze candidates: prediction extension (index
*changes* vs subsequent volatility changes, with controls, modest
framing), weighting exploration, per-episode case pages.

## Honest limitations

Association, not causation. Salience, not ground truth — anniversary
coverage counts by construction (disclosed in methodology §7). GDELT
reaches back to Jan 2017 only. Not investment advice.
