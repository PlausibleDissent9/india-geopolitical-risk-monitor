# Prospective institutional precision audit — execution plan

The v2 500-item package is a current-regime pilot. Its 11-day source window is
retrospective and partly predates the 2026-08-03 rubric lock, so it may diagnose
failure and exercise the external-coder system but cannot license a historical,
prospective, or “better than another index” claim.

The confirmatory study is a separate future registration. Its source window is
the first 90 complete UTC score-days beginning 2026-08-08 (through
2026-11-05), fixed before any label. No day may be selected or removed because
of its score, topic, event status, source mix, provisional precision, or another
system's output. Missing source files are a frame failure, not an exclusion.

Planned design:

- Use the production matcher directly, with dictionary, matcher, raw-source,
  seed, frame and sample hashes frozen before coding.
- Draw up to 500 matched production document instances per channel by
  known-probability stratified sampling across day and normalized-story
  cluster; report both document-instance and cluster-aware intervals. A
  channel with fewer than 500 eligible instances is
  a census of the frame and cannot borrow evidence from another channel.
- Send the same items in independently frozen random orders to two external
  coders. Primary estimates remain coder-specific; no consensus or adjudicated
  number may replace them. A masked third review may be published only as a
  clearly secondary diagnostic.
- Require at least 400 firm labels per coder and channel. Each coder/channel
  passes only if the registered 95% lower confidence bound is at least 0.80.
  Per-channel reliability additionally requires at least 400 firm overlaps,
  raw agreement at least 0.90 and Gwet's AC1 at least 0.70; constant-label
  overlap is not identifiable, never an automatic pass.
- Publish every channel, abstention, disagreement, interval, failure and
  deviation. The precision study does not estimate recall; the independent
  recall protocol remains a separate population and label exercise.

Any comparison with CI/AI-GPR must apply both systems to the same frozen corpus
and clearly separate construct differences from classification performance.
No superiority sentence is licensed unless the prospective precision study,
the independent recall study, reproducibility gate and predeclared comparison
scorecard all pass.
