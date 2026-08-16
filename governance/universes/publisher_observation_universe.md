# Universe: publishers observed by the receipt-identity lane

**Universe id:** `uni:igrm.publisher.receipt_observation`
**Inclusion rule:** `rule:publisher.observed_in_available_channel`
**Implementation:** `src/entity_emitter.py`

---

## What this universe is

Every publisher domain that appeared in an **available** receipt-identity
channel on the release's reference date, and nothing else.

It is a universe of *observation*, not of importance. Membership means
the receipt lane saw an article at that domain on that day. It does not
mean the publisher is significant, reliable, Indian, or relevant to
geopolitical risk. Those are all separate claims and none of them is
asserted here.

## The inclusion rule, exactly

A domain is included if and only if:

1. it appears in `docs/data/receipt_identity.json` for the reference
   date, **and**
2. the channel it appeared in has `state == "available"`, **and**
3. the article carrying it produced an `evidence_item` record, **and**
4. the domain matches `^[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?$`.

All four are mechanical. There is no scoring, ranking, or judgment step,
which is why this universe can exist while events cannot: selecting a
domain is deterministic, whereas classifying a headline into an event
class needs a registered coding rule that does not exist.

## What is excluded, and why

**Domains in unavailable channels.** When GDELT refuses a channel, the
lane records `state: "unavailable"` and holds no articles for it. Those
publishers are absent from this universe not because they were judged out
of scope but because nothing was observed. On 2026-08-15 two of five
channels were unavailable, so this universe is a partial view of the
day's press and must be read as one.

**Everything not seen.** The lane requests at most five articles per
channel under a seven-request budget. A publisher that published on the
reference date but did not appear in that sample is excluded. This is a
sampling boundary, not an editorial one.

**Publishers observed on other dates.** Each release is dated. A domain
seen on a different day belongs to that day's release.

## The denominator this supports

The honest denominator is *"domains observed in available channels on the
reference date"*. Any rate computed over this universe has that
denominator and no other. In particular it does **not** support:

- a share of Indian press coverage
- a share of all coverage of a topic
- any claim about publishers that were not sampled

## Stability and supersession

The rule is deterministic, so re-running it against the same receipt
payload reproduces the same membership. If the payload changes — the lane
retries and fills a previously unavailable channel — the resulting
universe is a **new release**, not an edit of the old one. The prior
release remains valid for what it observed.

## Known weaknesses

- The sample is small and hybrid-relevance ordered, so it favours what
  GDELT ranks highly rather than a random draw.
- Domain is taken as published by the provider and not independently
  resolved, so a redirect or an aggregator domain is recorded as itself.
- Two channels being unavailable on the reference date makes this a
  three-fifths view. That is stated in the release rather than smoothed.
