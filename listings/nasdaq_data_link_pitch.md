# Nasdaq Data Link contributor pitch — IGRM

**Dataset:** India Geopolitical Risk Monitor — daily press-salience
percentiles for five registered channels of India-relevant
geopolitics, 2017-present, with a pre-registered public validation
record.

**Why it belongs on a market-data platform, honestly framed:** IGRM
measures press attention, not risk, and makes no forecasts — a
discipline stated on every page. What it offers quant users is a
clean, reproducible, daily attention series with (a) frozen ex-ante
construction (no lookahead from dictionary tuning), (b) published
sampling uncertainty, (c) an event-study layer showing measured
historical associations with Indian market series (n and CIs stated,
Benjamini-Hochberg corrected, association language enforced), and
(d) descriptive comparison with the academic GPR-India index (monthly
r=0.48, zero shared pipeline), indicating limited co-movement between
related measures rather than validation.

**Delivery:** static CSV/JSON over HTTPS, CORS-open, no auth
(https://igrm.in/data/history.csv); field stability under a versioned
public API contract; daily by ~06:30 IST with a public reliability
record that lists its own misses.

**Licensing:** data CC BY 4.0 — free tier appropriate; attribution
required.

**Contact:** Ishan Krishna, ishankrishna9@gmail.com, https://igrm.in
