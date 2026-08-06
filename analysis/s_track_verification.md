# S-track source verification record (2026-08-06)

Only verified sources build; this file records what verification
actually found, including the dead ends. Guessed endpoints are how
instruments quietly rot.

## S1 — RBI DBIE (in progress, state recorded precisely)

data.rbi.org.in is an Angular SPA over an open JSON gateway. VERIFIED
tonight from the portal's own traffic: `POST /CIMS_Gateway_DBIE/
GATEWAY/SERVICES/dbie_foreignExchangeReserves` returns weekly total
reserves (latest ~$682.4B, correct magnitude, Fridays) with schema
`body.resultList[].{amount, timeDate, fxReservesCode}`. NOT yet
captured: the request envelope (empty body returns 400; the SPA
served cached data during spying, so no live request body was
observed). Fallback route confirmed on the same page: the Weekly
Statistical Supplement / Handbook publication links. Next session:
capture the envelope with spies installed before first load, or
parse the WSS publication files. No fetcher ships until one of those
is real.

## S9 — Indian Ports Association (pending verification)

Not yet probed. Traffic reports historically publish as PDF/XLS;
format verification before any build.

## S10 — Global Terrorism Database (founder-gated)

GTD requires license registration — an account, therefore the
founder's step by hard limit. Machine builds the fetcher the day the
credentials exist.

## S11 — ICEWS: VERDICT, dead as a live source

ICEWS was discontinued 2023-04-11 (Harvard Dataverse; maintainer
changelogs concur). A feed frozen in 2023 cannot cross-validate a
live 2017- instrument — that is the finding, and no ICEWS lane will
be built for the live index. Two honest uses remain: (a) the frozen
archive overlaps the M1 historical proxy era and could join that
study's context; (b) POLECAT, its successor, is the real candidate
for live event-stream cross-validation and gets its own verification
before anything builds.
