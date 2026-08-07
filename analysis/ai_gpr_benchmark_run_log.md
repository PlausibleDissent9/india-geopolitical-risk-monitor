# AI-GPR India benchmark: execution record

## Frozen inputs

- Public registration commit: [`58ca6c007c477855cccdb207a48356019fc8a08a`](https://github.com/PlausibleDissent9/india-geopolitical-risk-monitor/commit/58ca6c007c477855cccdb207a48356019fc8a08a)
- Registration SHA-256: `7c82a0549432ba5daefc0ea525f7802fa207959d87c7b9072c148da56b288370`
- Frozen analysis-script SHA-256: `9578f6ccdc01dd7ec6e8677548ffdf5376ae8e08bea2c8b242436c7d2e621de0`
- Pinned AI-GPR source SHA-256: `22750ad1e1bf0e3420f87a0810da3fbebf00d308d67d103ee5a236db3d9d17e3`
- Pinned IGRM history SHA-256: `79885e7bf472a66faf48d8ee50e7fcc9a909171e4e2d8106a4f20ed46d24b32c`

The GitHub commit and its HTTP 200 response were independently checked before the first
invocation. The registration file was then submitted to four OpenTimestamps calendars.
The proof is committed as `analysis/ai_gpr_benchmark_registration.json.ots`; it remains a
pending attestation until a calendar anchors it in Bitcoin.

## Invocation log

1. The first invocation used the repository's Python 3.9 environment. It stopped when
   pandas attempted to import SciPy for Spearman correlation. No statistic was returned
   and no output file was written.
2. The second invocation used the isolated Python 3.12 test environment. It stopped at
   the same missing indirect dependency. Again, no statistic was returned and no output
   file was written.
3. SciPy 1.18.0 was installed in the isolated environment. No code, input, hash, method,
   seed or decision rule changed. The unchanged frozen script then completed against the
   pinned local source bytes.

The missing dependency is an operational deviation, disclosed here and repaired in
`pyproject.toml`. There were no analytical deviations from the registration. The generated
result is published verbatim at `docs/data/ai_gpr_benchmark.json`, SHA-256
`f91fb4cc27e7acd0e7f2a131a57a0ebf43b33096897253dda872f541308981a2`.

## Registered result

The primary Spearman correlation between month-over-month changes is **0.256** across 106
consecutive-month pairs. The registered six-month moving-block 95% interval is
**[0.050, 0.407]**; the twelve-month robustness interval is **[0.082, 0.364]**. The frozen
decision sentence is: **The two measures share a common component but are far from
redundant.**

This comparison does not establish that either measure is more accurate. They measure
different constructs over different corpora.
