# Independent adversarial review protocol for IGRM Max

Status: review contract. It grants no publication or signing authority.

## Purpose

The second resident agent must not merely reread a diff or confirm that tests are
green. It must attempt to disprove the capability being shipped. The builder owns
implementation and primary QA; the reviewer independently reconstructs the
claim, attacks the failure boundary and reports only evidence-backed findings.

## Inputs for every review

The review packet must identify:

- exact base and candidate commits;
- exact changed-file set and intended capability claim;
- public routes, payloads, schemas and workflows affected;
- declared input frames and denominators;
- rights, privacy, security and safety decisions in scope;
- generation and reproduction commands;
- tests added or changed and the committed surface they assert; and
- known limitations that must remain visible.

The reviewer reads committed candidate bytes. Uncommitted working-tree state is
not evidence for a release judgment.

## Required attacks

### Truth and construct

- replace observed values with null, zero, stale and plausible-but-wrong values;
- exchange attention, event, exposure, probability, causal and forecast labels;
- attempt to make a partial frame appear complete;
- introduce a hidden denominator change;
- create double-counting through duplicate, hierarchy or syndication paths; and
- make one valid source conceal one ineligible source.

### Time and revision

- move publication, observation, effective, retrieval and knowledge-cutoff dates
  independently;
- introduce future knowledge into a historical replay;
- revise or delete a source after release;
- split or merge an episode without changing its count; and
- verify that old releases remain independently interpretable.

### Rights, privacy and security

- substitute an unsigned, expired, revoked or unrelated rights decision;
- expose restricted bytes through public payloads, caches, logs or assistants;
- attempt prompt, evidence and retrieved-content instruction injection;
- test path traversal, unsafe URLs, formula injection and identifier spoofing;
- verify key isolation and missing-signature refusal; and
- test rollback, restore and correction behaviour after compromise.

### Product and accessibility

- render every affected route at phone, tablet and desktop widths;
- inspect console/network health, keyboard order, focus, labels and reduced motion;
- test no-JavaScript, low-bandwidth and partial-payload states;
- follow every changed route and evidence link from a public entry point; and
- compare visible values, units and dates with their exact payload fields.

### Reproducibility and operations

- rebuild in a clean extract without untracked local inputs;
- delete expected outputs before regeneration;
- tamper with one input, manifest field and output;
- verify workflow permissions and bot-push enforcement;
- simulate a late-stage failure and ensure publication remains atomic; and
- confirm the review procedure never executes unauthenticated archive code.

## Capability-specific World and Episode attacks

For the World State Matrix and Global Episode Ledger the reviewer additionally
must attempt:

- a geometry member omitted from one layer;
- an observation outside the registered member universe;
- an unavailable cell presented as zero or safe;
- a candidate event presented as confirmed;
- two syndication-related sources presented as independent;
- one real event represented as two episodes and two real episodes merged;
- event, episode and observation counts interchanged;
- a country with no sources silently removed from the denominator;
- a correction that fails to update every dependent product; and
- a map or assistant statement whose evidence bundle cannot be resolved.

## Verdict rules

The reviewer returns:

- `BLOCK` for any P0/P1 truth, rights, security, denominator, temporal,
  publication or contract failure;
- `PASS_WITH_FOLLOWUP` only for bounded non-blocking issues with an owner; or
- `PASS` when independent attacks found no blocking defect.

A review cites file, line/object path, reproduction steps, observed result,
expected result and smallest honest repair. The reviewer may not generate a
founder signature, external label, adoption claim or rights approval. The
builder may not convert silence, timeout or unavailable tooling into a pass.
