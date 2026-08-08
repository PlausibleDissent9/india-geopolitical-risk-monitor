# What a real India dependency edge requires, and why none exists yet

Status: requirements note, not a contract. Nothing here licenses a
claim. Written 2026-08-08 against `governance/source_rights_registry.json`
as committed, to specify what the Atlas needs before a single edge can
be published as anything but synthetic.

## The finding

**Fourteen sources are rights-registered. Not one of them can establish
a dependency edge between two entities.**

That is not a criticism of the registry — every source in it does the
job it was registered for. It is a statement about what the October
Atlas actually needs, which is a different kind of data than IGRM has
ever ingested.

| Registered source | What it yields | Can it link entity to entity? |
|---|---|---|
| GDELT DOC / NGrams / GKG | press attention, receipts, tone | No — attention, and an aggregator besides |
| GDELT Events v1, UCDP GED, COW MIDs | coded events | No — events, not dependencies |
| IMF PortWatch | transit counts at **four chokepoints** (hormuz, bab_el_mandeb, suez, malacca), from 2019-01-01 | No — chokepoint level, no Indian port, no firm |
| JODI oil | national energy aggregates | No — country totals |
| Yahoo Finance | listed instrument prices | No — prices, not dependencies |
| Wikimedia Pageviews | public attention | No |
| Caldara–Iacoviello GPR / AI-GPR | comparator indices | No |
| Natural Earth | map geometry | No — geometry, not relationships |
| IGRM public payloads | first-party derived | Only what we already computed |

The nearest miss is PortWatch, and it is not close: four global
chokepoints is a maritime bottleneck series, not a map of which Indian
firm depends on which port for which commodity.

## Why the gap cannot be closed by inference

The repository already forbids the shortcut. `authority_class:
aggregator` sources (GDELT) are registered for attention and receipts
and must never become a factual input — an aggregator's presence in a
corpus is evidence that something was *reported*, never evidence that a
dependency *exists*. Deriving "firm X depends on port Y" from
co-occurrence in news text would be exactly that substitution, and it
would be indistinguishable, in the payload, from a measured edge.

The Sensor Fusion lane already names this: an edge in the "News
observation" lane may not be read as event magnitude, and the eight
lanes exist precisely so a press mention cannot be laundered into a
physical fact.

## What a publishable edge must carry

From the Exposure DNA and Sensor Fusion schemas as built, an edge is
publishable only with all of:

1. **Both endpoints inside a declared universe frame**, registered
   before the edge is measured, with an explicit inclusion rule and an
   as-of date. Membership cannot be decided after seeing the data.
2. **A source whose rights permit publishing the derived value** — not
   merely reading it. Redistribution of a derived quantity is a
   different permission from access.
3. **An original denominator carried through.** "Freight share" must
   stay in freight-share units against the denominator the source used,
   never rescaled into a comparable-looking percentage.
4. **A knowledge time distinct from the valid time**, so a later
   correction cannot leak backwards — the property the knowledge-replay
   engine already enforces.
5. **An explicit gap when absent.** Missing edges are named, never
   interpolated and never dropped from the denominator.

Any edge failing one of these is synthetic, and must stay labelled the
way tonight's fixtures are labelled.

## The four edge classes, by distance

**Port ↔ commodity throughput** is the closest to reachable. India
publishes port-level cargo statistics through the Ministry of Ports,
Shipping and Waterways and its major port authorities. Requirements
to settle before any fetch: whether the terms permit republishing
derived shares; whether coverage spans only the major ports or the
non-major ports too, which decides the denominator; and what the
revision policy is, because a restated month must enter as a new
knowledge time rather than overwriting an earlier one.

**State ↔ commodity exposure** is next. DGCI&S and the Ministry of
Commerce publish trade by commodity, and UN Comtrade mirrors national
submissions. Requirements: commodity classification version and its
mapping stability across years; whether state attribution exists at
all in the source or would have to be inferred, which would make it
unpublishable; redistribution terms.

**Firm ↔ commodity or firm ↔ port** is far. It requires either
transaction-level customs records or firm disclosures. The former is
generally restricted and commercially licensed; the latter is
unstructured, filed at irregular intervals, and self-reported. Neither
is a weekend acquisition, and firm-level claims carry legal exposure
that no other lane in this project carries.

**Chokepoint ↔ India** is partially available today via PortWatch, but
only as transit counts through four global chokepoints. To make it an
India dependency it would need Indian-flagged or India-destined traffic
specifically, which the current series does not separate.

## Coverage denominators

Every claim needs its "of what", and the denominator must come from the
declared universe rather than from whatever the data happened to cover.
Concretely, before publishing any coverage percentage:

- the universe frame states how many ports / commodities / states are in
  scope and by what rule they were included;
- the payload reports covered-count over frame-count, not over
  rows-we-obtained;
- entities in the frame with no data are listed by name, because "100%
  known gaps surfaced" is only true if the gaps are enumerable.

A coverage figure computed over obtained rows is the single easiest way
to publish a number that is arithmetically correct and substantively
false.

## The honest bottom line

The machinery is ahead of the data, and by a wide margin. The schemas,
the refusal codes, the two-clock replay, the eight-lane separation and
the append-only route floor are all built and tested. What does not
exist is a single registered source capable of populating one real edge.

That makes the October dependency universe a **licensing and
acquisition problem, not an engineering one**. The next decision is
Ishan's: which of the four edge classes to pursue first, knowing that
port-commodity throughput is plausibly obtainable from public Indian
sources and firm-level exposure is not obtainable this quarter without
a commercial licence and a legal review.

Until one is acquired and registered, every exposure edge on the site
stays labelled synthetic — which is exactly what tonight's fixtures do.
