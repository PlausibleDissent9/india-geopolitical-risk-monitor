# IGRM Max — India Geopolitical Intelligence Operating System

Status: **governing north-star specification; most capabilities are targets, not current claims**

Effective: 2026-08-08

This document replaces the July 2026 “maximum version.” That design described a
stronger press-salience index. The new objective is larger: build the most useful,
auditable and India-specific public geopolitical intelligence system possible.
It must help a researcher reproduce a result, a business trace an exposure, a
journalist verify a claim and a public institution understand the evidence behind
a reading.

IGRM does **not** currently claim superiority over any benchmark. No “best,”
“leading” or comparative-performance claim is licensed until the corresponding
test in Part VIII passes on frozen evidence and the result is published, including
negative results. Ambition sets the test; evidence earns the claim.

---

## I. The objective

IGRM Max is not one magic number and not a chatbot placed over a chart. It is a
versioned measurement and decision-support system joining six things that other
products usually keep separate:

1. **attention** — what India-relevant geopolitical subjects receive press and
   public attention;
2. **events** — what observable geopolitical actions occurred, with evidence and
   coding uncertainty;
3. **exposure** — which Indian states, sectors, firms, routes, assets and
   commodities connect to those events;
4. **transmission** — what changed in trade, freight, energy, markets and policy;
5. **capacity and response** — what can absorb the shock and what institutions
   actually did; and
6. **confidence** — how complete, current, corroborated and reproducible each
   statement is.

These layers stay separate. They may be viewed together, but an attention reading
never silently becomes an event probability, an event count never becomes an
economic-loss estimate, and a market move never becomes evidence of causation.

### The atomic promise

No public analytical claim renders unless its complete machine-validated
evidence bundle is present. The only exception is a predefined abstention or
limitation template. Every rendered claim resolves through one chain:

```text
claim
  -> typed fact(s)
  -> transformation and version
  -> observation(s) or coded event(s)
  -> exact evidence item(s)
  -> source, retrieval time, rights status and content hash
```

The build fails on an orphan source ID, unsupported transformation, invalid
temporal join, incompatible rights status, stale evidence or missing typed
uncertainty. Every page, assistant answer and analytical API response carries an
immutable bundle hash. If the chain breaks, the system abstains or displays the
limitation. A polished answer is never allowed to outrun its evidence.

### The unit of advantage

The moat is the **India exposure graph**, not a composite. One registered event
can connect to actors, locations, treaties, routes, ports, commodities, sectors,
listed firms, states, policies and observed outcomes. That creates a reusable
research object instead of a disposable daily score.

### Current capability and explicit non-goals

At the effective date of this specification, the mature public core is a
five-channel press-salience series with research and diagnostic layers. IGRM-E,
IGRM-X, IGRM-T, IGRM-C and IGRM-Q below are a target architecture, not finished
instruments. The public evidence-locked assistant is already part of the served
surface, under its existing closed truth boundary; no public lane may claim the
new publication guard until it completes the wiring gates below. There is no
complete external precision/recall result, comprehensive event frame, declared
exposure universe, licensed forecast, government adoption or minted research DOI.

IGRM Max is not intended to replace official intelligence, field reporting,
company due diligence or professional emergency judgment. It will not issue
policy directives, security assurances, investment recommendations or a universal
geopolitical “truth score.”

---

## II. The measurement system

### A. Evidence plane

All downstream products depend on an append-oriented evidence plane containing:

- exact request and retrieval metadata;
- source and publisher identity;
- publication and observation timestamps;
- original language and machine-readable translation provenance;
- content or response hashes;
- licensing and redistribution status;
- parse and transformation versions;
- duplicate, syndication and correction relationships; and
- a link from every consumed record to the run that selected it.

Public evidence may contain full bytes only where rights and privacy permit it.
Otherwise IGRM publishes citations, hashes, structured extracts and access
instructions without pretending to relicense third-party material.

Every source must first enter a machine-readable acquisition and rights register
with: owner/provider; legal or contractual basis; permitted fields; access,
retention, quotation, redistribution and derived-data rules; geographic and
historical coverage; source version; retrieval target; outage fallback; expected
cost and cost owner; reproducibility tier; review date; and the signed decision
that authorizes each public use. A product cannot publish from an unregistered or
expired rights decision. A release states whether independent reproduction needs
licensed inputs, rather than equating open code with open reproduction.

Sources receive separate roles rather than being blended indiscriminately:

- **official record:** Indian ministries, Parliament, regulators, gazettes,
  multilaterals and foreign-government releases;
- **coded events:** event datasets and independently coded primary material;
- **news attention:** diverse registered news corpora;
- **public attention:** pageviews and search-interest sources where their terms
  permit use;
- **physical transmission:** shipping, port, energy, trade and logistics data;
- **financial transmission:** India-relative market and hedging measures; and
- **expert evidence:** signed, attributable judgments with conflicts disclosed.

Paid data is justified only when it materially improves a registered coverage,
latency or rights problem. No vendor is purchased merely to increase a source
count.

### B. Canonical event and claim registry

Every event receives a stable ID and typed fields:

- what happened and what remains alleged;
- start, end and knowledge timestamps;
- actors and roles;
- locations and geographic precision;
- event class, intensity and direction;
- India-relevance path;
- supporting, contradicting and superseded claims;
- independent-source count and source diversity;
- coder/model provenance and adjudication status; and
- uncertainty, missingness and revision history.

Models may propose candidates. They may not create public ground truth. High-impact
events require a registered rule or human adjudication, and corrections never erase
the earlier vintage.

### C. India exposure graph

The graph joins events to the Indian economy and state through versioned edges:

```text
Actor / country / event
        |
        +-- route / chokepoint / port / border
        +-- commodity / technology / treaty / sanction
        +-- Indian state / ministry / sector / listed firm / critical asset
        +-- exposure type, magnitude, direction, source, date and confidence
```

Edge types include import dependence, export dependence, freight dependence,
energy dependence, supplier concentration, ownership, operational presence,
border proximity, treaty obligation, sanctions reach, cyber dependency and
policy jurisdiction. An unknown magnitude stays unknown; qualitative edges cannot
masquerade as quantified exposure.

#### Declared universes and coverage denominators

The graph cannot be evaluated if its boundary is whatever happens to have been
mapped. Every release therefore freezes explicit universes and inclusion rules.
The initial pilot should use enumerated public frames such as:

- Indian states and union territories from one dated administrative register;
- registered major ports, selected land crossings and declared critical routes;
- HS-6 commodities present in a dated India trade frame;
- a frozen listed-company universe such as a named index membership vintage;
- sectors from one versioned classification; and
- public critical assets only where a lawful authoritative register exists.

Each universe publishes included, excluded, unmappable and stale counts. Coverage
is a denominator, not a narrative. Independent samples measure edge precision,
recall or known-unknown rate, staleness, and missingness by country, sector and
state. An unmapped entity remains visible as unmapped; it is never dropped from
the denominator.

### D. Six registered output families

IGRM Max publishes a family of instruments rather than hiding incompatible
constructs inside one score.

| Family | Measurement object | Primary output | Forbidden interpretation |
|---|---|---|---|
| IGRM-A | India-relevant attention | source-specific salience series | probability or severity |
| IGRM-E | coded observable events | event counts/intensity with uncertainty | complete ground truth |
| IGRM-X | India exposure | typed graph edges and concentration metrics | realized loss |
| IGRM-T | observed transmission | trade, freight, energy, market and policy movements | causation without design |
| IGRM-C | capacity and response | buffers, diversification and institutional actions | guaranteed resilience |
| IGRM-Q | evidence quality | freshness, coverage, corroboration and reproducibility | substantive safety |

The current five-channel press-salience series becomes IGRM-A, preserving its
history, versions and limitations. It is not relabelled as the whole system.

### E. Summary views

The default interface is a **state vector**, not an unexplained master score:

```text
Attention | Events | Exposure | Transmission | Capacity | Confidence
```

A summary index may be studied only after the constructs and weights are
registered, sensitivity is published, missing layers cannot be silently
renormalized, and decision-task evidence shows that the summary adds value over
the vector. Components remain available even if a summary is later licensed.

---

## III. The intelligence products

### 1. Public live terminal

The public home surface answers four questions immediately:

1. What changed?
2. What evidence supports it?
3. Where could India be exposed?
4. How certain and current is the reading?

The terminal carries completed-day and intraday lanes separately, displays
revision status, works without JavaScript, meets WCAG 2.2 AA, remains usable on
a 375-pixel phone, and stays fast on ordinary Indian mobile connections.

### 2. Event dossier

Each event page combines a timeline, evidence ledger, competing claims, actors,
map, India-exposure paths, observed transmission, related policy, data vintages
and exportable citations. The page distinguishes confirmed fact, coded inference,
third-party allegation and IGRM interpretation visually and in machine-readable
form.

### 3. Research workbench

Researchers can:

- query every versioned series and event;
- download a citation-ready subset and manifest;
- reproduce a chart from an immutable vintage;
- inspect dictionaries, code, missingness and corrections;
- run registered alternative specifications;
- obtain DOIs for stable releases; and
- cite a precise data slice, not only the homepage.

### 4. Business exposure workbench

A business supplies no confidential data by default. It can select sectors,
commodities, corridors and geographies to see registered exposure paths, scenarios
and evidence. A private deployment may accept firm data only with explicit data
governance, isolation, deletion and human-review controls. Outputs remain scenarios,
not predictions or investment advice.

### 5. Government and public-policy mode

The institutional mode provides jurisdiction-aware event timelines, ministry and
state exposure views, policy-response tracking, source corroboration and briefing
exports. It must be usable in read-only/offline environments, preserve an audit
trail, state uncertainty, and never claim official endorsement without written
authorization.

### 6. Journalist and public mode

Embeddable charts, citation cards, plain-language definitions, correction badges
and evidence links let a journalist verify rather than repeat IGRM. Every embed
states its unit, date, vintage and limitation even when separated from the site.

### 7. Evidence-locked assistant

The assistant is a query interface over registered facts, not an oracle. A model
may classify a question and select a finite answer plan. It may not supply public
numbers, prose, dates, citations or confidence. A deterministic verifier resolves
facts, checks dates and denominators, and renders the answer with a fact ledger.

The maximum answer surface adds:

- historical and cross-event queries;
- graph traversal (“why is this relevant to Indian fertilizer?”);
- researcher mode with query manifests and code pointers;
- business mode with registered exposure edges;
- multilingual question understanding; and
- tier-one evidence retrieval with source diversity and rights disclosed.

“At least 50 articles” is a display target only when 50 eligible, rights-safe
items exist. The system publishes pool size, deduplication method, selection rule
and cap; it never invents or pads evidence to satisfy the layout.

---

## IV. Technical architecture

### Registered data objects

The core objects are `Source`, `Retrieval`, `EvidenceItem`, `Claim`, `Event`,
`Entity`, `ExposureEdge`, `Observation`, `Metric`, `Vintage`, `Correction`,
`Study` and `AnswerBundle`. Each has:

- a stable ID and schema version;
- created, observed, effective and superseded times where applicable;
- provenance and rights fields;
- typed units and denominators;
- confidence and missingness with explicit semantics;
- content hashes; and
- parent transformations or evidence links.

### Storage and publication

- An append-oriented object store retains licensed evidence and run manifests.
- A relational store enforces typed entities, events and observations.
- A graph projection serves exposure traversal; it is rebuildable from the
  canonical relational/event log rather than becoming an unaudited truth store.
- Immutable release snapshots remain downloadable as JSON/CSV/Parquet.
- OpenAPI and JSON Schema define public contracts.
- Public pages render server/static-first; JavaScript enhances rather than owns
  the core evidence.
- Every pipeline promotes staged outputs atomically after all gates pass.

### Cadence lanes

| Lane | Purpose | Publication rule |
|---|---|---|
| intraday | provisional attention/event candidates | visibly provisional, never overwrites final |
| daily | completed news-day instruments | atomic, freshness-checked and versioned |
| weekly | human-authored analytical note | evidence-linked and separately signed |
| monthly | research release and reliability report | frozen vintage and correction digest |
| event-driven | material correction or official action | append-only incident/change record |

### Reliability and security

Public status reports source age, lane age, completeness, revision state and
incidents separately. Target service objectives are measured only after a stable
baseline. Secrets never enter questions, evidence payloads or client code. Model
budgets, rate limits and kill switches sit outside the model. Every user-facing
HTML insertion uses safe text or allowlisted links.

---

## V. Truth, uncertainty and study program

### Study 1 — measurement precision and recall

The first binding research gate is a prospective production-linked study with:

- a complete captured scoring frame;
- registered estimands that match the score's contribution units;
- inclusion probabilities and weighted estimators;
- independent double coding and blinded adjudication;
- precision and recall reported separately by channel;
- finite-population or design-appropriate intervals;
- all exclusions and frame failures published; and
- no label access before the sample, code and analysis plan are frozen.

No machine or founder diagnostic substitutes for this result.

### Study 2 — event-layer agreement

Blind coders compare IGRM-E against registered official/event-data frames. The
study reports missed events, false inclusions, temporal error, actor/location
error, disagreement and unobservable regions. Agreement with another dataset is
not automatically truth; adjudication and source review remain explicit.

### Study 3 — robustness and bias

Publish sensitivity across dictionaries, languages, outlets, countries,
normalization windows, thresholds, deduplication rules, missing-source policies
and alternative weights. Report source concentration, geographic/language gaps,
anniversary effects and negative placebo results with the same prominence as
favourable results.

### Study 4 — decision utility

Researchers, business analysts and journalists complete frozen tasks in a
randomized crossover design using IGRM and a declared baseline. Primary outcomes:

- factual accuracy;
- calibrated confidence;
- task completion time;
- citation/evidence error;
- abstention quality; and
- user ability to identify uncertainty.

Government evaluation is a separately governed pilot. Testimonials are not a
substitute for a task study.

### Study 5 — forecasts, only as a separated laboratory

Any forecast is a distinct experimental product with preregistered targets,
training cutoffs, no-lookahead tests and strong naive baselines. Use proper scores
such as Brier/log loss for probabilities and publish calibration, discrimination
and failure. A losing model remains published and never contaminates descriptive
IGRM-A/E/X/T/C/Q outputs.

### Study 6 — reproducibility and resilience

An independent clean environment verifies every rights-permitted released value,
manifest and schema. Disaster-recovery drills verify that another maintainer can
publish a correction, rebuild the site and rotate credentials from documented
procedures.

### Study 7 — benchmark comparisons

Before access to comparison outcomes, each benchmark study freezes:

- the construct, population, geography, time window and baseline vintage;
- task/sample construction and an independent evaluator;
- primary metric, minimally important effect and superiority/non-inferiority rule;
- power or precision target;
- multiplicity policy and secondary-outcome labels;
- missing-data, exclusion and stopping rules;
- public anonymized/raw results to the extent rights permit; and
- a permanent loss register.

Only the exact predeclared dimension may receive a comparative claim. Passing one
task never licenses overall superiority; missing the threshold is recorded as a
loss, not reframed after inspection.

---

## VI. Governance that can survive success

### Decision separation

- The founder signs construct definitions and public interpretations.
- Code and transformations require review and green gates.
- Human coders remain independent of model suggestions and prior labels.
- AI drafts and classifications are always identified in provenance.
- Commercial sponsors receive no undisclosed influence over scores, sources or
  publication timing.

### External review structure

Build a small methods and users council covering measurement, Indian foreign
policy, economics, data engineering, journalism and business continuity. Members
review registered changes and incidents; they do not silently edit results.
Conflicts, compensation and dissents publish.

### The operating institution

Global-index quality requires continuous ownership, not only schemas. The
24-month operating plan names, funds and separates at least these functions:

| Function | Accountable work |
|---|---|
| methods lead | constructs, studies, uncertainty and benchmark protocols |
| source/rights steward | acquisition register, licensing, privacy and provenance |
| research/coder lead | frames, coder independence, adjudication and field operations |
| data/engineering lead | pipelines, schemas, releases and reproducibility |
| SRE/security owner | reliability, incident response, access, backups and abuse controls |
| editor/user-research lead | claims, explanations, corrections and decision-task studies |

One person may cover several functions during the build phase, but no high-impact
event, construct change, label adjudication or material correction may depend on
unreviewed single-person judgment. Dual control, reviewer identity and dissent are
recorded.

For calibration labels specifically, the founder personally makes every ruling,
as required by `GOVERNANCE.md`. A separate human reviews the evidence and process
and records agreement or dissent; registration and public use remain blocked
while dissent is unresolved. That review neither delegates nor substitutes the
founder's ground-truth authority, and a machine may not fill either role.

The plan progresses through founder/fractional expert build, paid independent
coding and pilot operations, then durable engineering/editorial coverage. Vendor
quotes and rights decisions determine the budget; invented cost precision is not
planning. Before institutional mode can be described as ready, the public lane
must have funded continuity, succession and credential-escrow procedures, tested
incident recovery, an external security/privacy review, API abuse controls, a
data-protection assessment for any private user data, and a completed pilot.

### Permanent honesty surfaces

The corrections ledger, negative-results register, vintage browser, reliability
record, rights inventory and limitations page are first-class products. Nothing
material disappears because it is embarrassing.

---

## VII. Adoption, citation and recognition

Recognition is an output of use and evidence, not a website adjective.

### Research adoption

- Correct ORCID identity and connect releases/works.
- Publish citation metadata, stable authorship and a DOI-backed data release.
- Preregister external studies before labels or outcomes are available.
- Release a software paper only when the package, history, governance and
  independent research use satisfy the venue's actual rules.
- Provide teaching notebooks and replication examples.

### Public and institutional adoption

- Publish a weekly evidence-linked note without missing cadence silently.
- Offer stable embeds and a low-friction API.
- Produce sector/state case studies co-reviewed by domain specialists.
- Recruit pilot users who agree to publish what helped and what failed.
- Make Indian-language access a measured product, not translated decoration.

### Recognition targets

Awards, media, university visibility and public-sector attention are pursued only
with specific evidence packages: a working instrument, externally reviewed study,
documented users, reliability history, corrections record and a founder narrative
that accurately separates what was built from what remains targeted.

---

## VIII. Benchmark contract: what “outperform” must mean

There is no universal leaderboard across unlike instruments. IGRM may claim a
benchmark-specific advantage only after a frozen comparison on that exact
dimension passes. Until then every row below is a target.

| Benchmark | Strength to absorb | IGRM Max target | Required proof before any advantage claim |
|---|---|---|---|
| Caldara-Iacoviello Geopolitical Risk Index | academic legitimacy, long vintages, country history | deeper India decomposition, fact-to-exposure traceability | peer-reviewed or externally reviewed construct study; public vintages; equal-period benchmark tests |
| ACLED Conflict Index | event coding, geographic and actor detail, frequent updates | connect coded events to India exposures and downstream evidence | blinded event agreement/error study plus latency and geographic-coverage audit |
| International Country Risk Guide | decision-oriented political/economic/financial structure | transparent, traceable India business scenarios | analyst task study on accuracy, time, calibration and evidence error |
| Economic Policy Uncertainty Index | disciplined text-index design and academic use | multi-source India-specific uncertainty/attention decomposition | registered construct, precision/recall and out-of-sample robustness studies |
| World Uncertainty Index | cross-country comparability and long panel | India depth without losing explicit comparability | common-schema country panel and invariance/comparability audit |
| Global Peace Index | public reach, indicator architecture, weight robustness | higher-frequency evidence and transparent sensitivity | published weighting/missingness sensitivity and public comprehension study |
| Fragile States Index | mixed quantitative/content/expert workflow | source-level provenance and signed expert disagreements | independent audit of coding, conflicts, reproducibility and revision history |
| INFORM Risk Index | hazard–exposure–vulnerability–capacity separation | live India exposure and capacity graph at sector/state/route level | audited graph coverage, edge accuracy and decision-task utility |
| Global Supply Chain Pressure Index | connection to physical supply-chain pressure | geopolitical attribution and India corridor/sector specificity | out-of-sample transmission study against naive and GSCPI baselines |
| Baltic Dry Index | narrow, trusted real-economy signal | explain India-relevant route/commodity transmission without diluting the physical measure | licensed/reproducible inputs, route coverage and timeliness evidence |
| Worldwide Governance Indicators | source aggregation, uncertainty and reproducibility | fact-level provenance and uncertainty on every IGRM family | independent reproduction plus uncertainty/calibration audit |
| BlackRock Geopolitical Risk Dashboard | decision-focused investor experience | public evidence, research exports and India-specific workflows | blinded UX/task benchmark with accessibility, latency and correctness gates |

### System-level victory conditions

IGRM Max reaches its intended ceiling only when all of these are true:

1. **Truth:** externally coded precision/recall and event studies are complete,
   not merely designed.
2. **Traceability:** every analytical statement resolves to an evidence bundle.
3. **Utility:** IGRM wins preregistered user tasks against declared baselines.
4. **Reliability:** a long public history shows scheduled delivery, failures and
   corrections without selective deletion.
5. **Reproducibility:** independent users recreate every rights-permitted release
   value from authenticated inputs.
6. **Coverage:** the system measures and displays source, language, geography and
   exposure gaps rather than hiding them.
7. **Accessibility:** mobile, assistive-technology, low-bandwidth and multilingual
   evaluations pass.
8. **Adoption:** independent researchers cite it and real external users document
   consequential use.
9. **Governance:** methods, conflicts, AI roles, rights and corrections withstand
   external review.
10. **Restraint:** the system abstains when evidence is insufficient and never
    turns salience into risk, association into cause, or scenario into forecast.

No single favourable correlation, award, citation or government meeting satisfies
this contract.

The target is a Pareto improvement on narrow declared dimensions, not an honest
claim that one young system has already surpassed GPR's historical depth, ACLED's
field network, ICRG's expert operation or the Baltic Dry Index's market role.
Those are institutional advantages that may take years to approach. IGRM's
credible route to distinction is deeper, more transparent India-specific exposure
traversal with measurable coverage and a harder evidence boundary.

---

## IX. Execution program

Nothing in the maximum version is sacrificed; sequencing prevents an attractive
feature from outrunning the measurement beneath it.

The founder-authorized launch denominator is registered in
`design/igrm_max_launch_contract.json`: eight pillars, eleven engines and twenty
required capabilities for 24 October 2026. `python -m src.max_launch_contract`
fails if that scope shrinks, a milestone silently drops an engine, or completed
work lacks exact product, implementation and refusal-test blobs at its named Git
commit. Repository progress cannot stand in for citations, adoption, awards or
study observations that do not yet exist.

### Program 0 — make the existing instrument unimpeachable

- finish prospective precision/recall infrastructure and field the studies;
- close known reproduction, rights, freshness and semantic gaps;
- maintain a green, atomic daily pipeline;
- finish citation metadata, ORCID and rights-safe release preparation; and
- preserve the evidence-locked assistant's closed truth boundary.

### Program 1 — build the common intelligence substrate

- register schemas for sources, claims, events, entities, observations and
  exposure edges;
- publish a source/rights/coverage catalog;
- add run-to-evidence lineage and immutable vintages;
- implement official-source and event candidate ingestion; and
- expose missingness and corroboration as data.

### Program 2 — build the India exposure graph

- start with energy, shipping and trade corridors where public data is strongest;
- connect commodities, chokepoints, sectors and states;
- add expert-reviewed, sourced mappings with effective dates;
- quantify only edges with defensible denominators; and
- release graph snapshots and correction history.

### Program 3 — ship the product family

- state-vector homepage and event dossiers;
- researcher query/export workbench;
- sector/state exposure explorer;
- journalist embeds and public-language views;
- evidence-locked assistant over the expanded fact catalog; and
- institutional briefing exports and alert bundles.

### Program 4 — earn comparative claims

- field the six studies in Part V;
- publish the benchmark scorecard, including losses;
- obtain independent methods and rights review;
- run external pilots; and
- license only the narrow advantage claims that passed.

### First implementation slices

1. Canonical scope, claim-eligibility and source-rights contracts with build-time
   validators and public coverage denominators.
2. Machine-readable benchmark registry and proof-state scorecard.
3. Versioned `Source`, `EvidenceItem`, `Claim`, `Event` and `ExposureEdge`
   schemas with adversarial validation tests.
4. Public source/rights/coverage catalog.
5. Official-source event candidate lane with no model-written public facts.
6. Energy–shipping–trade exposure graph pilot and exact evidence traversal.
7. Event dossier generated from the canonical objects.
8. Research export bundle with subset manifest and citation.
9. Expanded assistant catalog, only after every preceding object is verifier-safe.

Each slice lands code, data/schema, documentation and the tests that assert the
same committed surface. A feature is not complete because its UI exists; it is
complete when its evidence, contract, correction path and failure behaviour exist.

---

## X. Non-negotiable boundaries

- No unsupported composite pretending to summarize every geopolitical dimension.
- No model-generated factual prose on a public path.
- No undisclosed source, weight, override, sponsor or correction.
- No “live” badge derived from branding rather than measured freshness.
- No article cap described as a denominator or complete evidence set.
- No cross-date join without an explicit temporal relationship.
- No external redistribution without a rights decision.
- No forecast claim without a frozen, out-of-sample benchmark.
- No comparative claim based on incomparable periods or constructs.
- No public-institution endorsement claim without written evidence.

The maximum version is therefore not the project with the most features. It is
the project in which the largest useful surface remains inside one enforceable
truth boundary.
