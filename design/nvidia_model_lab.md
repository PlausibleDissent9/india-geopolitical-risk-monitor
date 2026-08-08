# NVIDIA model lab — sealed review fleet, not an autonomous coder

Status: implemented local evaluation boundary; candidate models remain
unbenchmarked and have no production authority.

IGRM can use NVIDIA's hosted NIM catalog to make review broader without making
truth depend on model consensus.  The lab admits one bounded UTF-8 artifact,
scans it for common credential formats and prohibited paths, calls one
registered model, and accepts only a strict local JSON review schema.

The credential lives in macOS Keychain under service `igrm-nvidia-api`.  The
CLI has no API-key flag and no environment fallback.  The registry contains no
secret.  Redirects are refused so an authorization header cannot be carried to
another host; response type and size are bounded; provider errors collapse to
stable non-sensitive refusal codes.

## What the fleet is for

- coding models attack a diff for correctness, security and missing tests;
- reasoning models attack a claim or method for construct and provenance gaps;
- an India-language model attacks translations and local-language ambiguity;
- later, safety models can test the public assistant's prompt-injection and
  unsafe-advice refusals.

The models are deliberately heterogeneous.  Agreement is not a vote and is
not evidence.  A finding matters only if a human integrator can reproduce it
from the code, data or cited source and the ordinary IGRM gate then passes.

The scanner is a narrow backstop for common credential formats and prohibited
repository paths.  It is not a general PII, copyright, confidentiality or
data-rights classifier.  The operator remains responsible for supplying only
public, rights-cleared material; uncertainty means do not send it.

## Authority boundary

The lab cannot write the repository, commit, push, publish, label a validation
sample, adjudicate evidence, approve a rights decision or authorize a public
claim.  It receives no tools or GitHub credential.  Restricted/paid-source raw
data, personal data, unreleased coder labels, signed decision material and
confidential legal advice are prohibited inputs.

`candidate_unbenchmarked` means exactly that.  Each model must first run on a
frozen suite of historical IGRM defects plus clean controls.  We will publish
per-task recall, false-positive burden, invalid-JSON rate, latency and model
vintage.  Only narrow task assignments that beat the declared baseline may be
retained; losses remain in the register.

Catalog presence is only discovery, not capability.  A separate live probe
must demonstrate that the account can call the model within the local timeout
and that the response passes the exact review schema.  HTTP refusal, timeout,
invalid JSON and schema drift are measured failures; the adapter does not
repair, extract or reinterpret a near-valid answer.

## Local use

```bash
python -m src.nvidia_model_lab catalog
python -m src.nvidia_model_lab review \
  --task code_review \
  --model poolside/laguna-xs-2.1 \
  --input /tmp/igrm-candidate.diff
```

Output is advisory JSON on stdout.  A refusal is JSON on stderr with a stable
code and non-zero exit.  No review is wired into publishing or the public
assistant.

Provider reference: <https://docs.api.nvidia.com/nim/reference/llm-apis>
