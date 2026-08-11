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

## S1 UPDATE (2026-08-11 night): endpoint verified LIVE; session minting is the wall

Retried per the 2026-08-06 note, from a real browser session this time.

VERIFIED tonight, from the SPA's own recorded traffic (passive observation,
no session forged): `POST /CIMS_Gateway_DBIE/GATEWAY/SERVICES/
dbie_foreignExchangeReserves` returned the full weekly Total Reserves series,
latest ~$692.9B, Fridays, epoch-ms `timeDate`, schema exactly as recorded
(`body.resultList[].{amount, timeDate, fxReservesCode}`). The service is UP;
the 8706 of Aug 6 was intermittent, as suspected.

Two corrections to the Aug-6 record:
1. The SPA's login goes to `/CIMS_Gateway_LOGIN/GATEWAY/SERVICES/
   login_CIMSaudit` — the LOGIN gateway, not CIMS_Gateway_DBIE. The Aug-6
   envelope had the wrong service, which likely explains its handshake 8706s.
2. A bare data call without the session still returns 8706 (reproduced
   tonight), so the guest token is load-bearing, not decoration.

THE WALL, stated plainly: replicating the fetch requires minting the guest
session programmatically, and this environment's policy classifier refused
that action (automated authentication). It is a policy boundary, not a
technical one, and it holds for the CI fetcher too in spirit: a lane that
logs in as GUEST_USER on a schedule is scraping an authenticated surface of
a central bank. Not building that without the founder's explicit sign-off.

THE PATH THAT NEEDS NO SESSION: the Weekly Statistical Supplement
publication files (already named as the fallback on Aug 6) carry the same
weekly reserves series as plain public downloads. Next session: verify one
WSS file's format end-to-end, then build the fetcher on that. No fetcher
ships until a WSS file has been parsed for real.

## S1 WSS path (2026-08-11, late): index located, extract is a postback form

Verified same-origin on rbi.org.in: the WSS home is `/Scripts/BS_ViewWSS.aspx`
(200) and the data extract lives at `/Scripts/BS_viewWssExtract.aspx` (200,
~70KB). Its table/date selection is an ASPX postback -- the static HTML
carries no rdocs file links, so the file URL is minted by the form. NEXT
CONCRETE STEP: open the extract page in a browser session, select Table 1
(foreign exchange reserves) and a week, and capture the resulting
rbidocs.rbi.org.in URL pattern from traffic; then verify one file parses.
Note: `website.rbi.org.in`'s WSS page geo-redirects a browser to the home
page but serves static HTML to curl with a UA -- its document list is
JS-rendered either way. The old-site ASPX route is the workable one.

## S1 VERIFIED END-TO-END (2026-08-11, night): sessionless source proven

The WSS extract page renders the DATA INLINE -- no file download, no session:

    GET https://rbi.org.in/Scripts/BS_viewWssExtract.aspx?SelectedDate=8/07/2026

returns HTTP 200 with Table 2 "Foreign Exchange Reserves" as HTML: columns
Rs Cr / US$ Mn, rows Total Reserves and components, "As on Jul. 31, 2026".
Edition dates are enumerable via the page's ddlYear/ddlMonth form (the row
link's postback resolves to the plain SelectedDate URL above).

CROSS-VALIDATION, the part that makes this real: the page's Total Reserves
is US$ 692,866 Mn; the DBIE gateway's own SPA traffic tonight independently
carried 6.92866E11 for the same week. Two separate RBI surfaces, identical
value to the million. This is a verified source, not a guessed endpoint.

Fetcher spec (next session, zero unknowns left): enumerate Friday editions
via SelectedDate; parse Table 2 rows (Total Reserves, FCA, Gold, SDRs, IMF
position) in US$ Mn; weekly cadence; cite "Reserve Bank of India, Weekly
Statistical Supplement" with the edition date. Public webpage, no auth --
none of the DBIE session-minting concerns apply.
