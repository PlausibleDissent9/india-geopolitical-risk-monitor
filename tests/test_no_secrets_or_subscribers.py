"""Two standing constraints, enforced instead of remembered.

  * Subscriber emails never enter the public repo, its logs, or its
    pages. The list lives at ~/igrm-private/subscribers.csv, outside the
    working tree entirely.
  * Credentials never enter the repo. They go into GitHub repo secrets
    and are read from the environment.

Both are the kind of rule that holds until one hurried commit, and the
cost of breaking either is unrecoverable: a pushed secret is burned, and
a pushed subscriber list cannot be unpublished.

Audited when written: four distinct email addresses in the whole tree,
all of them intentional, and no credential-shaped string outside an HTML
input placeholder.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

# Every address allowed to appear anywhere in the tree, with why.
ALLOWED_EMAILS: dict[str, str] = {
    "actions@github.com": "the CI bot's commit identity",
    "ishankrishna9@gmail.com": "the author's own contact and citation",
    "kalev.leetaru5@gmail.com": (
        "GDELT's maintainer, whose public contact address appears "
        "verbatim inside GDELT's own rate-limit error text and in the "
        "drafted outreach note"),
    "you@example.com": "a documentation placeholder",
}

SECRET_RE = re.compile(
    r"sk-ant-[A-Za-z0-9_-]{8,}"
    r"|ghp_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AIza[0-9A-Za-z_-]{30,}"
    r"|-----BEGIN (?:RSA |OPENSSH |)PRIVATE KEY-----")

# Paths whose contents are third-party crawled text, not authored by
# this project: an address inside a fetched news headline is data.
DATA_PREFIXES = ("data/raw/", "docs/data/")


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT,
                         capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if line]


def _read(rel: str) -> str | None:
    p = ROOT / rel
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except (OSError, UnicodeDecodeError):
        return None


def test_no_unexpected_email_address_is_committed():
    """A subscriber address reaching the public repo cannot be
    unpublished, so the allowlist is exhaustive rather than indicative."""
    found: dict[str, list[str]] = {}
    for rel in _tracked():
        if rel.startswith(DATA_PREFIXES):
            continue
        text = _read(rel)
        if text is None:
            continue
        for addr in EMAIL_RE.findall(text):
            if addr.lower() not in ALLOWED_EMAILS:
                found.setdefault(addr, []).append(rel)
    assert not found, (
        "email addresses in the repo that are not on the allowlist "
        f"(subscriber leak?): { {k: v[:3] for k, v in found.items()} }")


def test_every_allowed_address_has_a_reason():
    for addr, why in ALLOWED_EMAILS.items():
        assert isinstance(why, str) and len(why) > 15, (
            f"{addr} is allowlisted without a stated reason")


def test_no_credential_is_committed():
    """Placeholders are permitted only where they cannot be a real
    secret: an HTML input's placeholder attribute, which is UI text."""
    leaks = []
    for rel in _tracked():
        text = _read(rel)
        if text is None:
            continue
        for m in SECRET_RE.finditer(text):
            line_start = text.rfind("\n", 0, m.start()) + 1
            end = text.find("\n", m.start())
            line = text[line_start:end if end != -1 else len(text)]
            if 'placeholder="' in line and 'type="password"' in line:
                continue
            leaks.append(f"{rel}: {m.group(0)[:12]}...")
    assert not leaks, f"credential-shaped strings committed: {leaks}"


def test_the_subscriber_list_is_not_tracked():
    """Match the DATA FILE, not any path containing the word.

    The first version matched `"subscriber" in path`, which passed here
    and failed the moment it was committed -- because this test file's
    own name contains "subscriber" and it flagged itself. It passed
    locally only while it was still untracked, so `git ls-files` could
    not see it. reproduce.sh caught it in a clean clone, which is
    exactly the difference a clean clone exists to expose.
    """
    tracked = [
        f for f in _tracked()
        if Path(f).name.lower() in ("subscribers.csv", "subscribers.json")
        or "igrm-private" in f.lower()
    ]
    assert not tracked, f"the subscriber list is in the repo: {tracked}"


def test_the_private_directory_is_outside_the_working_tree():
    """Not merely gitignored -- outside, so no `git add -f` or a
    reordered ignore rule can ever sweep it in."""
    assert not (ROOT / "igrm-private").exists(), (
        "igrm-private is inside the repo; it must live outside the "
        "working tree entirely")
