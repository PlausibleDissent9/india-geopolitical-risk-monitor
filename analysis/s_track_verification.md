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

## S1 UPDATE (2026-08-06 night): envelope recovered, server refusing

Reading the SPA's own bundle (main.*.js) beat runtime spying. The
request shape is now KNOWN, verbatim from their code:

    POST /CIMS_Gateway_DBIE/GATEWAY/SERVICES/dbie_foreignExchangeReserves
    headers: Content-Type: application/json, channelkey: key2,
             datatype: application/json, authorization: <session>
    body: {"body": {"currencyCode": "USD", "reserveCode": "TR",
            "fromDate": "YYYY-MM-DD 00:00:00",
            "toDate": "YYYY-MM-DD 00:00:00", "frequency": "Weekly"}}

The `authorization` value comes from a guest session minted by
`login_CIMSaudit` (username GUEST_USER). Tested tonight: BOTH the
audit handshake and the data call return errorCode 8706 "Internal
Server Error Occurred. Please try after some time" -- server-side,
not a client mistake (the browser session succeeded minutes earlier
against the same endpoints). Verdict: the shape is solved, the
service is intermittently unavailable. Retry on a later day before
writing the fetcher; if 8706 persists, the Weekly Statistical
Supplement publication files are the fallback path and carry the
same series.
