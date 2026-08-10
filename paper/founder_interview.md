# IGRM founder interview — draft answers

**Draft in Ishan's voice, for Ishan to correct.** Every number is pulled from
the published payloads and sourced at the bottom. Nothing about the instrument
is invented.

**Four answers contain things only you know, and I guessed. Marked 🔴 — rewrite
those or the paper has a fabricated premise in it:** Q1 (the origin event), the
second half of Q4 (what changed in your head), Q9 (who you actually want), and
the biographical fields at the end.

---

# The origin

## 1. What exact question were you trying to answer? 🔴 GUESSED — rewrite

I wanted to know whether the thing everyone says — "tensions are rising" —
was ever a measurement or just a mood. Every time something happened on the
border, the commentary was instant and confident and completely
unfalsifiable. Nobody could tell you if this week was louder than a random
week in 2019, because nobody had written the number down.

The existing indexes weren't wrong, they were just not about India. GPR is a
global index with India as a rounding error. You cannot take a series built
from US and UK newspaper archives and ask it what happened at Galwan. It will
answer, and the answer will be noise.

So the question was narrow and stupid on purpose: **on a given morning, how
much of the world's news is about India's five pressure points, and is that a
lot or a little compared to India's own past?** Not risk. Not forecast. Just:
is today loud, and loud relative to what.

> 🔴 The specific event or frustration is yours. If there was a particular
> day, a particular headline, a particular index you looked at and thought
> "this is not measuring my country" — that goes here and it is the sentence
> people will quote.

## 2. Why are the five channels the correct decomposition? Which one would a global index most badly misunderstand?

Because they are the five ways the outside world actually reaches India, and
they fail independently. Pakistan and China are the borders. Gulf is where the
oil comes from. US is where the trade rules get written. Shipping is the
physical chokepoints everything else has to pass through. A single "India
risk" number averages a border standoff with a tariff schedule, and those two
things have nothing to do with each other — they don't co-move, they don't
transmit the same way, and a user who cares about one does not care about the
other.

**Shipping is the one a global index cannot see at all.** Not "sees badly" —
structurally cannot see. I proved this by accident building the 1979–2019
extension: shipping has no actor-pair coding, because there is no country the
Strait of Hormuz is in a bilateral relationship with. Any index built on coded
events between countries has a blind spot exactly where India's energy import
route is. That is not a small gap for an economy that imports ~85% of its
crude.

The channel I'd defend least confidently is `gulf_energy` — its narrow-
dictionary robustness is **0.527**, the lowest of the five. It's genuinely
sensitive to wording. I publish that number rather than the average.

---

# What the instrument taught you

## 3. Which finding genuinely surprised you?

**Fusing four sources made it twelve times worse.**

I built the India Stress Gauge because it was obviously the right thing to do
— press, events, market, Wikipedia, weights registered in advance, four
independent windows onto the same thing. Combining independent measurements
is supposed to reduce noise. That's the whole premise of doing it.

It detects **2 of 29** episodes. Hit rate **0.069**. The press channel on its
own detects **24 of 29**.

I sat with that for a while. The honest reading is that the four sources
aren't four views of one thing — they're four different things, and averaging
them mostly cancels the signal that was in the press series to begin with.
Markets are already priced. Wikipedia is demand-side and slow. Events are
sparse. Weighting them together produced a number that is smoother, more
sophisticated-looking, and much worse at its job.

The reason I keep it on the site is that it is the strongest argument I have
against my own instinct. Sophistication is not accuracy. The simple thing won
by a factor of twelve.

Runner-up, and it's close: **the market moves first.** Largest association at
**lag −8** — India-VIX percentile changes tend to precede attention changes by
about eight trading days. Association, not causation, and I'm careful about
that. But it kills the most commercially attractive story about this index,
which is "watch the press to get ahead of the market." You don't. The market
got there first. I'd rather publish that than sell the other thing.

## 4. Which miss or failure made IGRM better?

The one that actually changed how I work: **I proved a gap was recoverable by
testing the wrong window.**

There's a hole in the series, 15 June to 1 July 2025. I went to check whether
the upstream source still had those days, ran the probe, got data back, and
concluded the outage was on my side and fixable. It wasn't. The probe had
sampled 5–12 June — **zero overlap with the gap**. I had run a test, gotten a
green result, and the test had not touched the thing it was supposed to be
testing. The real check showed the days are gone upstream and are not coming
back.

Same shape as another one: my blind-spot detector reported it worked on
**523 of 523** episodes. Perfect scores are not good news. It was searching
for the peak only *after* the episode ended, so the answer was true by
construction. Fixed, it's 521 of 523 — a worse number and an actual one.

🔴 **What changed in my head:** I stopped treating a passing test as evidence
and started asking what the test would look like if the thing were broken. If
I can't describe the failure it would catch, it isn't a check, it's a badge.
Now nothing goes in unless I've run it against the broken version first —
every test I wrote this week, I ran against the pre-fix code to watch it fail.

> 🔴 That last paragraph is my read of what your process became, not your
> words. If the actual shift in your thinking was different — and it probably
> was more specific — replace it.

## 5. Why expose numbers that make the project look worse?

Because they're the only reason to believe the good ones.

I publish: precision **uncalibrated** at 16 of the 100 labels I promised
(agreement 0.875, on n=16, and I print the n). Placebo overlap **45.2%** —
115 fake episodes, 52 of them collide with real ones, which is a weak result
and the first thing a hostile referee will find. The gauge's 6.9%. **Zero of
39** sector cells surviving multiple-comparison correction. Two back-extension
channels **withheld** for failing their own pre-registered test.

Anyone can publish a good number. What you cannot fake is a bad number
computed by the same pipeline, on the same schedule, on the same page, in
public, before anyone asked. The unflattering numbers are the audit trail for
the flattering ones.

There's a selfish version too: it makes the project un-embarrassable. Nobody
can find something bad about IGRM and reveal it, because it's already the
fourth link on the homepage. That is a much more comfortable position than
hoping nobody looks.

---

# The intellectual claim

## 6. If IGRM does not predict risk, what is it useful for at 6 AM?

It tells you where you are, not where you're going.

Concretely: it answers "is this normal?" A channel reads 88. That means today
sits in the top 12% of its own last two years. Not "risk is high" — that's
a different claim I don't make. Just: this is unusually loud for this channel,
by this channel's own standards, and here are the articles that made it loud.

That's useful because the alternative is vibes. Someone asks how serious the
Pakistan situation is this week and the honest answers are usually "feels
bad" or "worse than last month, I think." IGRM replaces that with a number
you can check, a two-year window it's ranked against, and the receipts
underneath.

And I'd rather be clear about the limit than sell past it: **the market moves
about eight days before the press does.** So this is not an early-warning
system for anything financial. It is a measurement of attention, taken every
morning, that you can audit. That's the whole product.

## 7. What does the Hindi Wikipedia result change about "Indian geopolitical salience"?

It puts a modifier in front of it that the name doesn't carry.

English Wikipedia tracks this index more closely than Hindi Wikipedia does on
**5 of 5 channels**, in both levels and day-to-day changes, and the gap is
**one-directional** — there is no channel where Hindi leads. That's not a
close call I'm interpreting generously against myself. That's five out of
five, both statistics, one direction.

So what I'm measuring is **English-language attention to India**, not Indian
attention to India. Those are different objects and I'd been using one name
for both.

I don't think that makes it less useful — English-language attention to India
is exactly what a foreign desk, a foreign investor, or a foreign ministry is
responding to, and there's an argument it's the more decision-relevant
quantity for the people who'd actually use this. But it's a different claim,
and the paper has to say the smaller true thing rather than the bigger
convenient one.

The reason I know this at all is that I went looking for it. Nobody made me
run the Hindi comparison.

## 8. Strongest claim you're willing to make? What would be dishonest?

**Strongest, and I'll say it at full strength:**

IGRM is a daily, fully public measure of India's press salience that is
**exactly reconstructable at the published score-cell layer from its own
documentation**: every current daily channel/composite cell must match, and a
missing cell fails rather than disappearing from the denominator. The check is
rebuilt every night by code forbidden from reading the production score
pipeline. This does not claim that non-redistributed market or acquisition
inputs can be recreated from a public clone. Every published vintage is diffed
for silent revision. Its
pre-registered episode detection recovers **24 of 29** events within ±3 days —
a naive any-channel detector recovers **26 of 29**, so that number is evidence
of channel attribution, not of detection, and I am not going to quote it
without saying so.
Its two border channels replicate against an independently built forty-one-
year proxy at **r = 0.89** and **0.85**, under filters frozen in a signed memo
before the first query ran.

I'd like someone to name another public index where a stranger can rebuild
every number from the codebook alone and get an exact match. I don't think
there are many.

**Dishonest, all of these:**

- that it predicts, forecasts or anticipates anything;
- that it measures **risk** — it measures press salience, and the difference
  is the entire point;
- that its precision is established — it's uncalibrated, 16 of 100;
- that the placebo test passed — 45.2% is not a pass;
- that fusing sources helped — it was 12× worse;
- that it measures Indian-language attention — 5 of 5 say otherwise;
- that the historical series is the index extended — different construct,
  never spliced, and I'd rather have two honest series than one long dishonest
  one.

---

# The end state

## 9. Who should use this first? 🔴 GUESSED — this is a strategy call, not a fact

**Academics first.** Not because they're the biggest audience — because
they're the audience the rest of the work already serves.

Everything I've built optimises for someone who needs to *cite* or *rebuild*
the series: the frozen API contract, the codebook, the nightly replication,
the vintage diffing, CC BY, the DOI. None of that matters to a trading desk
and all of it matters to someone putting IGRM in a regression.

The decision that gets easier: **you can use an India-specific attention
series without having to trust me.** Right now, if you want press salience for
India in a paper, you either use a global index that barely sees India, or you
build your own from scratch. IGRM is the third option, and the replication
result is what makes it a real option rather than a favour.

Journalists are the second audience and it's a much shorter path — "is this
week actually unusual" is a question they ask constantly and answer badly.

> 🔴 If you actually want investors or policymakers first, say so — it changes
> what gets built next, and I'd build a different thing.

## 10. In one year, what would make IGRM undeniable?

Two things, and neither is traffic.

**One: somebody I have never contacted cites IGRM in published work.** Not a
mention, a citation — meaning they used the series to make an argument and
were willing to attach their name to it. That's the moment it stops being my
project and starts being infrastructure.

**Two: somebody rebuilds the series from the codebook without emailing me.**
The machinery for that now exists and is measured every night. If a stranger
can reconstruct every currently published daily channel/composite cell from a
public page and never need to ask me a question, then that score transform is
genuinely independent of me. The broader upstream evidence boundary remains
explicit rather than being folded into that claim.

The greedy version: both, plus the 1979 series being the thing people cite,
because a forty-one-year India-specific attention measure that nobody had
before is worth more to the literature than another daily tracker.

---

# Short founder details 🔴 FILL THESE IN — I'm not inventing biographical facts

| Field | |
|---|---|
| Exact publication name | *suggest:* India Geopolitical Risk Monitor (IGRM) |
| Preferred affiliation line | *suggest:* Independent researcher, Bengaluru, India |
| ORCID | **blank — get one, it's free and ~2 min, do it before the DOI so they link** |
| Weekly hours until 1 Nov | |
| College deadlines that matter | |
| One person whose standard the paper must withstand | |

---

## Every number above, and where it lives

| Claim | File |
|---|---|
| 24/29 detection, placebo 45.2%, robustness 0.527 gulf | `docs/data/validation.json` |
| Gauge 2/29 = 0.069, registered weights | `docs/data/stress_gauge.json` |
| English leads Hindi 5/5, one-directional | `docs/data/wiki_hindi.json` |
| 0.893 / 0.848 publish; 0.216 / 0.153 withheld | `docs/data/back_extension.json` |
| 0 of 39 cells survive FDR 10% | `docs/data/sector_sensitivity.json` |
| VIX leads attention, lag −8 | `docs/data/priced_risk.json` |
| Precision uncalibrated, 16/100, agreement 0.875 | `docs/data/precision.json` |
| Complete published-cell blind reconstruction and denominator | `docs/data/replication.json` |
| Silent-revision tripwire | `docs/data/vintages.json` |
| Shipping has no actor-pair analog | `src/back_extension.py` |
| Gap 2025-06-15..07-01 unrecoverable | `NOTES` 0.25, `src/fill_gaps.py` |
| Blind-spot 523/523 → 521/523 | `src/blind_spot.py` |
