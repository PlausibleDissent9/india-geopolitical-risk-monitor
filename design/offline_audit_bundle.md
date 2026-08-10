# Offline audit bundle: design, attacks, acceptance tests

**Status:** design only. No code, no schema committed as normative, no route.
**Assigned:** Codex execution list item 2, 2026-08-10.
**Author:** Claude (agent), read-only pass over the committed verification
surface: `scripts/gate.sh`, `src/blind_replicator.py`, `REPLICATION.md`,
`docs/data/security_integrity.json`, the typed-canonical profile
(`igrm-typed-canonical-f64-v1`, Python and `docs/typed-canonical.js`), the
`.ots` OpenTimestamps registrations, and `docs/schemas/`.

---

## 1. The problem, stated precisely

Everything this project proves today is proved **online**. The gate runs in
CI, the blind replicator needs a checkout, the payload hashes live on the same
host as the payloads. A reviewer who distrusts the site has nothing they can
carry away; a reviewer in 2031 has nothing at all if the site is gone.

An offline audit bundle is one file that a stranger can download once and
verify forever, on an air-gapped machine, with no trust in the host that
served it.

The hard constraint that shapes everything: **the strongest evidence is not
redistributable.** Raw GDELT corpus, per-article receipts, market vintages —
all rights-restricted. The bundle must prove without containing. A design
that "just zips the repo and the raw store" is both a rights violation and a
16-GB non-answer.

## 2. The core move: ship commitments, not evidence

The bundle contains three strata, and the honesty of the design is refusing
to blur them:

    A. REDISTRIBUTABLE INPUTS   shares.csv, history.csv, dictionaries,
                                 payloads, codebook -- the public surface,
                                 included as bytes
    B. COMMITMENTS              typed-canonical digests of every non-
                                 redistributable input, plus the acquisition
                                 receipts' own digest tree
    C. TRANSFORMS               the exact code paths that map A to the
                                 published numbers, plus a one-page verifier
                                 spec runnable with stdlib alone

This yields two verifier tiers, and the bundle must state its tier claim on
the first page a reader opens:

- **T1 — anyone, offline.** Recompute every published score cell from
  stratum A via stratum C (this is `src.blind_replicator`'s existing claim,
  repackaged); check every digest in the manifest; check the release
  signature and the `.ots` timestamp proofs against the embedded Bitcoin
  block headers. Proves: *the published numbers are the deterministic image
  of the included public inputs, and existed before the timestamped moment.*
- **T2 — a rights-holding verifier.** Re-acquire upstream data under their
  own licence and compare against stratum B digests. Proves: *the committed
  inputs are what the upstream actually served.* The bundle enables this
  without performing it.

What no tier proves — and §9 registers it — is that the construct is valid,
that the sources are accurate, or that the founder's signing key was
uncompromised. A bundle is a chain of custody, not a truth machine.

## 3. The bundle is a release, not a snapshot

One bundle per published release, identified by the same
`source_release_sha256` the kernel already uses, never rebuilt in place. A
"latest bundle" that silently changes is the online trust model wearing a
zip extension.

    audit/igrm-audit-<release_sha12>.zip
    manifest.json          typed-canonical, self-digest excluded
    MANIFEST.sha256        flat sha256sum-compatible list, one line per member
    VERIFY.md              the one-page stdlib-only verifier spec
    verify.py              convenience runner (stdlib only; see A5)
    inputs/                stratum A bytes
    commitments/           stratum B digest trees + receipts metadata
    transforms/            stratum C: pinned source files, requirements hash
    timestamps/            .ots proofs + the block headers they anchor to
    signature/             founder signature over manifest.json

**Mutual pinning:** the bundle embeds the release's commit SHA; the site
publishes the bundle's sha256 in `security_integrity.json` and on the
downloads page. Neither artifact can be swapped without the other testifying.

## 4. Determinism, or the bundle cannot be re-audited

Two independent builds of the bundle for the same release must be
byte-identical, else "the bundle's hash is published" means nothing. This is
where zip formats fight back, and every one of these is a committed rule,
not a hope:

1. Member order: lexicographic by archive path, always.
2. Timestamps: every member's mtime is the release's commit time, UTC.
3. No platform bits: external attributes zeroed, no extra fields, no NTFS/
   Unix extensions, UTF-8 name flag set explicitly.
4. Compression: one registered method and level for every member.
5. Text bytes: members are committed bytes from `git archive` of the release
   commit -- never re-serialized JSON. Re-serialization is where float
   formatting and key order go to die; the typed-canonical profile exists
   for digests, not for round-tripping files.

Acceptance test 1 builds the bundle twice on two platforms and diffs bytes.

## 5. Refusal codes (builder-side)

Deny-by-default. The builder refuses rather than degrades:

    bundle_member_rights_ineligible      matches a rights-restricted glob
    bundle_member_untracked              not in the release commit
    bundle_member_digest_mismatch        bytes != release bytes
    bundle_release_unregistered
    bundle_signature_missing             founder signature absent -> no build
    bundle_timestamp_unverifiable        .ots proof does not verify locally
    bundle_manifest_incomplete           member on disk absent from manifest
    bundle_nondeterminism_detected       double-build digest mismatch
    bundle_verifier_nonstdlib_import     verify.py imports outside stdlib

`bundle_member_rights_ineligible` is checked against a **registered glob
list** (`governance/`), not against intuition at build time. The raw store's
paths are enumerable today: `data/raw/gdelt_chunks/`, receipts corpora,
market vintages. A new lane adding a restricted path must extend the
registry in the same commit — the same inventory-lock discipline the route
count already uses.

## 6. Attacks

**A1 — Bundle swap.** Serve a doctored bundle from the same URL. *Defence:*
mutual pinning (§3); the site-side hash is in a signed, sha256-pinned
registry file. The test asserts a bundle whose hash is absent from the
registry fails verification with a named error, not a warning.

**A2 — Stale replay.** Serve last month's genuine bundle as if current.
*Defence:* the bundle states its release SHA and date on VERIFY.md line 1;
the site's registry maps release → bundle hash. Staleness is visible, not
prevented — an offline artifact cannot know today's date, and pretending
otherwise would be theatre. Registered as a §9 limit.

**A3 — Selective bundling.** Publish bundles only for flattering releases.
*Defence:* the registry lists every release with `bundle: present|absent`,
and absence is itself an entry. Same move as the admission design's
universe receipt: make the denominator visible.

**A4 — Zip parsing games.** Duplicate member names (two `manifest.json`
entries, verifiers disagree on which wins), zip-slip paths (`../../`),
symlinks, absolute paths. *Defence:* the verifier spec REQUIRES rejecting
duplicates, non-relative paths, and links before any hashing; the builder
cannot emit them. Both directions tested with hand-built hostile zips.

**A5 — Trojan verifier.** The convenience `verify.py` inside a doctored
bundle "verifies" anything. *Defence:* the design's honest answer is that a
verifier inside the artifact it verifies is a convenience, never an
authority. VERIFY.md's first section says exactly that and gives the
independent path: five shell commands using system `sha256sum`/`python3`
stdlib against MANIFEST.sha256. `verify.py` is additionally constrained to
stdlib imports (refusal code above) so a reviewer can read all of it in one
sitting — but reading it is still the price of trusting it.

**A6 — Float drift.** A T1 verifier on ARM recomputes scores and gets
`54.50000000000001`. *Defence:* the recomputation spec inherits the blind
replicator's existing comparison discipline and the typed-canonical binary64
coercion; tolerances are stated in the manifest per-artifact (exact for
score cells, as today's replication claim already is).

**A7 — Timestamp forgery.** Fabricated `.ots` proofs. *Defence:* the bundle
carries the Bitcoin block headers its proofs anchor into, and VERIFY.md
shows the header-chain check offline. A verifier who wants full strength
checks the block hash against any chain copy they trust; with none, the
proof degrades to "internally consistent", and VERIFY.md says so plainly
rather than letting the weaker check impersonate the stronger.

**A8 — Rights leak.** A future payload embeds article text; the bundle
inherits it. *Defence:* the glob registry (§5) plus a builder-side content
screen for known receipt fields; a hit refuses the build. Tested with a
planted fixture.

**A9 — Commitment substitution.** Stratum B digests computed over doctored
raw data at build time. *Defence:* stratum B digests are not computed at
bundle time at all — they are copied from the digests the lanes committed
when the data was acquired (the receipts' own digest tree, already in git
history). The bundle proves custody from acquisition-time commitment
forward; it cannot retroactively strengthen acquisition. §9 states this.

## 7. Acceptance tests

1. **Byte-identical double build**, two platforms (§4).
2. **Air-gap verification**: T1 passes on a machine with networking removed,
   from the bundle file alone, in under ten minutes.
3. **Every refusal code reachable** by a test fixture; every code raised is
   registered (scrape `_fail(` — the clause layer's existing pattern).
4. **One flipped byte anywhere fails loudly**: flip one byte in each
   stratum in turn; verification names the member every time.
5. **Hostile zip corpus**: duplicate names, zip-slip, symlink, absolute
   path — builder cannot emit them, verifier rejects them.
6. **Rights screen**: a planted restricted-glob member and a planted
   receipt-shaped field each refuse the build.
7. **Registry round-trip**: bundle hash in the site registry matches, and a
   registry with the entry removed makes verification fail A1's test.
8. **The stdlib path works without the bundled verifier**: CI runs
   VERIFY.md's five commands verbatim on the built bundle.

## 8. First slice, and what stays out

**First slice:** builder + manifest + VERIFY.md + deterministic zip +
refusal codes + tests 1, 3, 4, 5 (hostile corpus can start with three
cases). Wire the bundle hash into `security_integrity.json`. One bundle,
for the current release, linked from the data page.

**Out of the first slice:** T2 tooling (a rights-holder comparison script),
per-vintage back-catalogue bundles, Zenodo deposit integration, and any
automation that builds bundles in a lane — the builder runs by hand until
its determinism has survived a week of releases. The 96-second-test lesson
applies: do not bolt a new cost onto thirteen lanes before measuring it.

## 9. Claim boundary, to be registered with the bundle

> The bundle establishes that the published numbers are the deterministic
> image of the included public inputs; that the non-redistributable inputs
> were committed to, by digest, at acquisition time and not altered since;
> that the release existed before its timestamp anchor; and that the
> archive you verified is the archive the site pinned. It does **not**
> establish that the sources were accurate, that acquisition-time
> commitments were honest, that the signing key was uncompromised, that the
> construct is valid, or that this is the newest release. Verification
> without an independent Bitcoin header source degrades the timestamp claim
> to internal consistency, and the verifier document says so.

## Open question for Codex

Whether the bundle's stratum C should pin the **whole repo tree** at the
release commit (simple, ~8 MB, but drags in every lane and test) or the
**transform closure only** (minimal, but the closure computation is itself
code that can be wrong, and a missed import quietly weakens T1 from "the
image of these inputs" to "the image of most of them"). I lean whole-tree:
the closure's failure mode is silent and the tree's failure mode is bloat,
and this project has been consistent that silent beats bloated in the wrong
direction. But it doubles as a distribution question — the tree includes
prose that rights-restricted upstreams may not want mirrored into an
archive marketed for permanence — so it is not mine alone.
