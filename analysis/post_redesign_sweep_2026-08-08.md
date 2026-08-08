# igrm.in — post-redesign production sweep

**Swept against** `origin/main` tip `8d2d2730c3c2e19041cee44f669be777cc6b63de`
("The chatbot answers what a reader asks first", 2026-08-08 16:03:22 +0530 = 10:33:22 UTC)
— 3 commits past the redesign `9d4d9aa`.
**Sweep window** 2026-08-08 10:39–10:50 UTC. **Method** curl, sequential, 0.25–0.4 s spacing.
**Repo access** read-only: `git fetch` + `git archive <sha> docs` extracted to scratch. Working tree untouched.

## Propagation state: FULLY PROPAGATED — zero lag

| Evidence | Value |
|---|---|
| Sitemap pages byte-identical to tip | **26 / 26** (sha256) |
| `/` `last-modified` | Sat, 08 Aug 2026 10:35:00 GMT (~98 s after tip commit) |
| `assistant_answers.json` `_meta.generated` | `2026-08-08T10:33:22Z` = tip commit second |

Measured push-to-CDN latency held (~90 s). **No finding in this sweep is PROPAGATION LAG.**
Every defect below is source-level and reproducible from the tip.

## 1. Sitemap pages — OK (26/26)

All 26 return **200**, non-empty, correct `<title>`, and the full redesign shell:
`<header class="masthead">` + `nav.mast-links` + `#theme-toggle` + `.skip-link` + `<footer>` + `<h1>`.

**Zero pages on the old shell.** The design pass is complete, not half-applied.
(An earlier strict matcher appeared to flag 25 pages; it required `class="masthead"` exactly
while 25 pages carry `class="masthead site-masthead"`. False alarm — corrected.)

Non-sitemap pages also checked: `404.html`, `embed.html`, `portal.html`, `write.html` — all 200,
all on the new shell except `embed.html`, which intentionally omits the masthead (iframe widget).

**Noted, not a defect —** two coexisting shells:

| | wrapper | stylesheet | body class |
|---|---|---|---|
| `index.html` | `.wrap nav-shell` | `style.css?v=24dccbe6` | none |
| other 25 | `.site-shell nav-shell` | `site.css?v=35b07296` | `site-page` + `data-page` + `data-root` |

`9d4d9aa` touched `index.html`, `style.css` **and** `site.css` together, so this is deliberate:
the homepage is bespoke and the system was extended *outward* from it. It is a standing drift
risk (two sheets, one masthead) but not a current defect — both render the identical markup.

## 2. Dead-link sweep — OK (0 dead)

112 distinct internal targets extracted from all 26 pages and fetched live.
**107 real targets, all 200.** The 5 non-200 are regex false positives — JS template-string
fragments inside inline `<script>` that the attribute matcher captured, e.g.
`receipts.html` → `href="' + esc(a.url) + '"`. Not emitted markup.

## 3. Versioned assets — OK (9/9, zero stale stamps)

All 9 distinct `?v=` assets return 200, and **every stamp equals `sha256(bytes)[:8]` of the
served file** — verified independently, not trusted:

`site.css` 35b07296 · `site.js` 88fb47ea · `style.css` 24dccbe6 · `app.js` e830352c ·
`fonts.css` 991014f5 · `labels.js` 7ba70543 · `motion.js` 5f04349d · `reveal.js` 33b267c3 ·
`vendor/chart.umd.min.js` 81ffafe1

**Zero unstamped css/js references** across all 30 HTML files. The restamp was clean.

## 4. CSP + external origins — OK (1 policy note)

- CSP meta present on **30 / 30** pages.
- **Zero external-origin scripts, styles, fonts, or images anywhere.** No external `url()` in any CSS.
- 5 fonts self-hosted, all 200 (`fonts.css` header: "Self-hosted 2026-08-04: no third-party font requests.").
- 19 external references exist, **all `<a href>` navigation** (github.com ×16, aeaweb.org, matteoiacoviello.com ×2). Not egress.

Declared egress, all three via `fetch()` so `connect-src` governs (no `form-action` conflict):

| Page | connect-src beyond 'self' | Status |
|---|---|---|
| `index.html` | `buttondown.com`, `formsubmit.co` | Permitted newsletter path |
| `portal.html` | `api.github.com` | **Policy note** — third origin, outside the stated "homepage newsletter only" rule. Correctly scoped to one operator page; not a leak. |

## 5. API contract — OK (86/86)

82 endpoints promised in `data/api_contract.json` (v2.2.1, frozen 2026-08-08): 76 JSON, 5 CSV, 1 RSS.
Plus 4 extras. **All 86 return 200 and parse in their promised format. Zero failures.**

Named new payloads, all live and parsing:

| Endpoint | Bytes | Parse |
|---|---|---|
| `data/assistant_answers.json` | 127,964 | JSON_OK, 26 answers |
| `data/outlet_drift.json` | 9,664 | JSON_OK |
| `data/multilingual.json` | 46,727 | JSON_OK |
| `openapi.json` | 105,834 | JSON_OK |
| `datasheet.md` | 21,159 | TEXT_OK |

CSV shapes sane: `history.csv` 3,307×7 · `shares.csv` 3,486×7 · `episodes.csv` 525×7 · `monthly.csv` 117×17 · `event_study.csv` 121×10.

## 6. Theme bootstrap — OK (identical on 30/30)

**One variant, byte-identical on every page** including the four non-sitemap pages:

```js
document.documentElement.dataset.theme = localStorage.igrmTheme || "dark";
```

Syntactically valid, no throw path (`localStorage` read is unguarded but cannot throw on a
same-origin HTTPS document). No divergence to reconcile.

## 7. Coherence — OK

| Check | Result |
|---|---|
| `latest.json` date | 2026-08-07 |
| `history.json` last date | 2026-08-07 (n=3306) |
| `history.csv` last row | `2026-08-07,…,55.9` |
| `history.json` last composite | 55.9 — **matches CSV** |
| `feed.xml` lastBuildDate | Sat, 08 Aug 2026 03:59:09 -0000 |
| `assistant_answers` `n_questions` vs `len(answers)` | 26 == 26 |
| `n_answered + n_refused` | 19 + 7 == 26 |
| by-status recount of `answers[]` | answered 19, refused 7 — **matches `_meta` exactly** |

Score/history/feed triangle is consistent. Assistant counts are self-consistent.

---

# DEFECTS

## D1 — Receipts lane stalled; silently disables 19% of the new Ask surface. **[rank 1]**

`data/status.json` `lanes[]` — every lane ran 2026-08-08 **except receipts**:

| Lane | Last |
|---|---|
| uncertainty | 2026-08-08T04:29:25Z |
| aptness | 2026-08-08T05:32:06Z |
| permanence | 2026-08-08T03:14:48Z |
| reliability | 2026-08-08 11:02 IST |
| **receipts** | **2026-08-07T18:02:08Z** ← one run behind |

Consequence, from `data/assistant_answers.json` `_meta.data_state`:
`score_date` 2026-08-07, `receipts_date` 2026-08-06, `"aligned": false`.

**5 of 7 refusals are `refusal_code: "evidence_date_mismatch"`** (the other 2 are the
by-design `forecast_or_advice`). So **5 of 26 registered questions (19%) refuse** on the
day `ask.html` shipped — not because the assistant is wrong, but because one lane didn't run.

The refusal itself is correct behavior and well-reasoned in `_meta`. The defect is the stall.

**Compounding — the freshness monitor cannot see this.** `data/freshness.json`:

```json
{"payload": "receipts.json", "generated": "2026-08-07", "age_days": 1,
 "max_age_days": 3, "status": "fresh"}
```

`receipts.json` is marked **fresh** while the assistant refuses on it. Freshness measures
*when the file was written*, not *what day it describes* — precisely the distinction commit
`992f750` named. No alarm fires on a condition that disables a fifth of the flagship surface.
Fix: add a described-day alignment check (`latest.json.date == receipts.json.date`) as its
own monitored invariant, distinct from write-time freshness.

## D2 — `feed.xml`: a 590-character RSS title. **[rank 2]**

`src/render_site.py:129-130`:

```python
first_line = n["markdown"].strip().splitlines()[0].lstrip("# ").strip() \
    if n["markdown"].strip() else n["week"]
```

`splitlines()[0]` takes the first *line*, not the first *heading*. `notes.json` records carry
only `{week, markdown}`; the 2026-W31 note has no leading `#`, and its opening paragraph is one
unwrapped line — so the whole paragraph becomes the title.

- W32 (has `# IGRM Weekly Assessment: …`) → title 63 chars. Correct.
- **W31 (no heading) → title 590 chars**, beginning "2026-W31 — The largest movement in this
  week's data was also the easiest to misread. …" and running to the end of the paragraph.

Every RSS reader renders that paragraph as the headline. Live now, 1 of 2 items in the feed.
Fix: only strip `#` when the line *is* a heading; otherwise fall back to `week` (or truncate at
~80 chars on a word boundary).

## D3 — `feed.xml`: no `<pubDate>` on any item. **[rank 3]**

`render_site.py:132-137` emits `<title>`, `<link>`, `<guid>`, `<description>` — no `pubDate`.
Confirmed absent in the served bytes. Readers fall back to fetch time, so items date themselves
to whenever the reader first polled, and chronological ordering is not guaranteed. The week is
already known (`n["week"]`, ISO week) — deriving a date is trivial.

## D4 — `feed.xml`: raw Markdown in `<description>`, cut mid-word. **[rank 4]**

`render_site.py:136`: `escape(n['markdown'][:400])` — no Markdown stripping, no ellipsis,
hard 400-char slice.

- W32 description opens `# IGRM Weekly Assessment: Week ending 6 August 2026` / `## Executive assessment` — the `#` glyphs render literally.
- Both items truncate mid-word: W32 ends "For a weekly assessment", W31 ends "alon".

Cosmetic relative to D2 but same function, same fix site.

## D5 — Subscribe modal is not gated as its comment claims; visitor emails relay to a personal inbox. **[rank 5]**

`docs/app.js`. The declared intent:

```js
/* … Gated on BUTTONDOWN_USER so visitors never see a
   flow that is not yet wired to a real list. */
const BUTTONDOWN_USER = "";  // buttondown.com username; empty = modal off
```

**The gate is not implemented.** `initSubscribe()` returns early only on
`if (!overlay) return;` — and `#subscribe-overlay` *is* present in the served `index.html`.
`BUTTONDOWN_USER` is consulted only inside the submit handler, never to suppress display.
So with `BUTTONDOWN_USER === ""` the modal still auto-opens after 15 s and takes the `else` branch:

```js
const res = await fetch("https://formsubmit.co/ajax/ishankrishna9@gmail.com", { … });
```

Live effect: a dialog promising "One concise institutional assessment each Friday" collects
visitor email addresses and relays them through a third party into a personal Gmail — no list,
no double opt-in, no welcome email, and the address is published in clear text in public JS
(a harvesting target). The comment asserts the opposite of the behavior.

**Pre-existing, not a redesign regression** — introduced in `55441aa`; `9d4d9aa` changed 7 lines
of `app.js`, none in this block. Reported because it is live and user-facing.

---

# Counts

| Class | Count |
|---|---|
| **OK** | 7 sweep sections (pages, links, assets, CSP, API, theme, coherence) |
| **PROPAGATION LAG** | **0** |
| **DEFECT** | **5** (D1–D5) |
| **UNREACHABLE** | **0** |

Checks executed: 26 pages fetched + hash-compared · 107 internal links · 9 versioned assets +
stamp verification · 30 CSP headers · 5 fonts · 86 API endpoints · 30 theme bootstraps ·
9 coherence assertions. **Total 302 live assertions, 297 pass.**

## Ranked shortlist — worth fixing

1. **D1 — receipts lane stall + freshness blind spot.** Only defect with analytical consequence:
   19% of the new Ask surface refuses, and nothing alerts. Two fixes — rerun the lane, then add
   described-day alignment as a monitored invariant so this is never silent again.
2. **D2 — 590-char RSS title.** One-line fix, publicly visible in every feed reader now.
3. **D3 — missing `pubDate`.** Same function; correctness of the feed as a feed.
4. **D4 — raw Markdown / mid-word truncation in descriptions.** Same function; cosmetic.
5. **D5 — ungated subscribe modal.** Not a redesign regression, but it collects personal data
   under a promise the code does not keep. Either implement the gate or wire a real list.

D2–D4 are all in `src/render_site.py:129-137` — one function, one commit.

## Incidental observation (not a defect)

`data/status.json` → `morning_contract`: `{"on_time": 0, "scored_days": 5, "rate": 0.0,
"last_scored_day": "2026-08-06"}`. The 6:00 AM IST publication contract has been missed on
**5 of 5 scored days**. Published truthfully on `status.html` — the instrument is honest about
it — but the rate is 0.0 and D1 is the same lane discipline surfacing again.
