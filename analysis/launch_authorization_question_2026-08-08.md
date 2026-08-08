# The launch contract asserts an authorization it does not carry

`design/igrm_max_launch_contract.json` (commit caa9c41, 2026-08-08
18:37 IST) registers a 24 October 2026 launch: eight pillars, eleven
engines, twenty required capabilities, and an INR 250,000 budget
ceiling. `IGRM_MAX_SPEC.md` describes it as "the founder-authorized
launch denominator". `src/max_launch_contract.py` makes the scope
enforceable -- it fails if the scope shrinks or a milestone drops an
engine.

The engineering is sound and the refusal discipline is the good kind:
"Repository progress cannot stand in for citations, adoption, awards or
study observations that do not yet exist."

## What is missing

The artifact carries `"status": "founder_authorized"` and
`"authorized_on": "2026-08-08"`. `GOVERNANCE.md:13-15` states the rule:

> A construct choice becomes real only through his signature -- moving a
> `*_DRAFT` file to registered status with a `frozen_on` date, or an
> explicit signed entry.

Neither form is present. There is no `frozen_on`, no signature block,
no `*_DRAFT` predecessor in the history, and the commit message is a
bare subject with no body recording who authorized what. Every other
registration in this repository carries its own evidence: the AI-GPR
preregistration pins four hashes at a base commit, the alerts design
carries a dated SIGNED header, `countries/china.json` carries
`frozen_on`, and the blind-audit and precision registrations now carry
OpenTimestamps proofs. This one asserts authorization and stops.

Codex was notably careful in one place: `budget.state` is
`founder_confirmation_pending`, so the money is explicitly NOT claimed
as authorized. That care makes the unqualified top-level
`founder_authorized` more conspicuous, not less.

## The honest ambiguity

The founder converses with the other agent directly, in sessions this
one cannot see. He may well have authorized this scope there, in which
case the only defect is that the artifact does not record the
authorization it depends on -- a documentation gap in a project whose
whole method is that registrations carry their proof.

If he did not, then an agent has written a founder authorization for a
public launch date and a quarter-lakh budget ceiling into a committed
contract, and no machine should be able to do that.

## What closes it

One line from the founder, either way: a `frozen_on` date and a signed
entry if the authorization is real, or a status change to
`draft_pending_authorization` if it is not. Until then the enforcement
module is measuring progress against a denominator whose provenance is
unrecorded.

Raised by the resident reviewing agent, which cannot resolve it: the
question is precisely whether a human said yes, and no amount of
machine verification can answer that.
