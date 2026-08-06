
## Probe run 2026-08-06 10:20 UTC

- DRY RUN: one day (2026-08-04), two columns = 0.00 GB
- LIVE: 39,351 links from 230 frontpages; billed 0 bytes
- VERDICT: within the 5 GB cap; a spike-days-only G2 lane is affordable at ~0.0 GB per queried day

## Probe run 2026-08-06 10:23 UTC

- recent 2026-08-04: 39,351 links from 230 frontpages (dry-run 0.00 GB)
- historical 2019-05-15: dry-run 6.9 GB exceeds the 5 GB cap; not queried live
- INTERPRETATION RULE (ex-ante): if the historical day shows orders of magnitude more frontpages than the recent day, the GFG has stalled and G2 is infeasible for the LIVE instrument (historical-study use only) -- an empty recent partition priced at 0 bytes is a husk, not a bargain.
