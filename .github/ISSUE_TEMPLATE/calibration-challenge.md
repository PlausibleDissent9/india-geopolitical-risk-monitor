---
name: Calibration challenge entry
about: "V19: submit probabilities on the open forecast questions before their windows open. Scored mechanically with the same Brier arithmetic as the registered arms; results publish."
title: "[challenge] "
labels: calibration-challenge
---

**Entry format** — one line per open question (ids and windows at
https://igrm.in/data/forecasts.json; only questions whose
`window_start` is still in the future score):

```
2026-08-10-pakistan_west: 0.55
2026-08-10-shipping: 0.40
```

**Rules, same as our own arms:** probabilities are frozen at your
comment's timestamp (GitHub's clock, not ours); entries after a
window opens are void for that question; outcomes are graded by the
registered spike detector; Brier per question, cumulative across your
entries. Your GitHub handle is your leaderboard name. Beat both the
climatology arm and the salience arm over 26+ resolved weeks and that
result publishes prominently — including the part where you beat us.
