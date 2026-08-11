# DBnomics provider request — IGRM

**Provider name:** India Geopolitical Risk Monitor (IGRM)
**Maintainer:** Ishan Krishna (independent researcher)
**Homepage:** https://igrm.in — **machine endpoint:** https://igrm.in/data/history.csv
**License:** CC BY 4.0 (data), MIT (pipeline)
**Update cadence:** daily, final by ~06:30 IST; public reliability
record at https://igrm.in/status.html

**Series offered (daily, 2017-present):** composite press-salience
percentile for India-relevant geopolitics plus five channel series
(Pakistan/western border, China/eastern border, Gulf & energy,
US & trade policy, shipping chokepoints). Units: percentile of each
channel's own trailing 730 days, 0–100.

**Construct, stated plainly:** press salience — the share of global
English news coverage matching registered channel dictionaries. Not a
risk measure; no forecasts. Methodology, validation record (24/29
pre-registered episodes, against 26/29 for a naive any-channel detector
and 6.8 expected by chance — the apparatus contributes channel
attribution, not detection), sampling bands, and per-article receipts
are public. A clean-room public command reconstructs every published daily
channel/composite score cell exactly; acquisition, receipts and market-derived
outputs have separately disclosed evidence/rights limits
(https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor/blob/main/REPLICATION.md).

**Stability commitment:** field names frozen under a versioned public
API contract (https://igrm.in/data/api_contract.json) with a stated
deprecation policy.

**Citation:** Krishna, Ishan (2026). India Geopolitical Risk Monitor.
https://igrm.in/
