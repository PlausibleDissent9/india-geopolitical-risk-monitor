# Founder authorization for IGRM Max

## Current state

The 24 October scope is registered but not founder-authorized. The contract's
`founder_authorization_pending` text is a proposal state, not a signature.
`python -m src.max_launch_contract --scope-only` verifies the proposal;
`python -m src.max_launch_contract` must refuse until all three public
authorization artifacts exist and verify.

## The one founder-only action

From the repository root, Ishan Krishna personally runs:

```bash
.venv/bin/python -m scripts.founder_authorize \
  --private-key /Users/ishankrishna9/.config/igrm/founder_authorization_ed25519.pem
```

The command has no non-interactive or `--yes` mode. It displays the registered
scope digest, requires the exact authorization challenge, asks for a 12+
character passphrase twice when creating the key, and signs only after those
inputs are supplied in an interactive terminal.

The encrypted private key is created outside the repository with mode `0600`.
It must never be committed, pasted into chat, uploaded to the website or given
to an agent. Keep an encrypted offline backup. The repository receives only:

- `governance/founder_signers.json` — the public key and its SHA-256 fingerprint;
- `governance/authorizations/igrm-max-2026-10-24.authorization.json` — the exact canonical statement; and
- `governance/authorizations/igrm-max-2026-10-24.authorization.sig` — the detached 64-byte Ed25519 signature.

After the founder runs the command, an agent may inspect those public artifacts,
run the verifier and commit them. An agent must not type the challenge, choose
the passphrase, unlock the key or create the signature.

## What the signature means

The signature authorizes the exact registered scope, 24 October launch date and
INR 250,000 ceiling. Any signed scope/date/ceiling change produces a different
digest and refuses verification. Evidence-backed progress is outside the
signature, so recording real progress does not silently change the mandate.

It approves no individual purchase. It is not scientific validation, legal
clearance, publication, adoption, citation, award or government endorsement.
Cryptographically, it proves control of the public key registered here. Stronger
public identity assurance requires Ishan to publish the key fingerprint through
an independently controlled identity surface; the repository must not claim
that external anchoring until it exists.

## Revocation and rotation

If the private key is lost or suspected compromised, do not delete history.
Record a dated `revoked_on` value for the old key, publish the incident in the
corrections/governance record, create a new key personally and sign a new
authorization statement. A key revoked on or before an authorization date is
ineligible.
