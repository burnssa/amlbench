"""The `independent` attestation tier cannot be self-issued from the OSS repo.

`--level independent` is the paid, server-driven tier (Cupel holds the held-out challenge
set, drives the customer's real endpoint, scores server-side; docs/CHALLENGE_PROTOCOL.md).
If a user could self-issue it, the strongest badge would be a free string. This proves the
gate refuses it while the weak `self-tested` tier is untouched.

No signing keys and no cert files are needed: the gate raises before any key access or
write, and the self-tested check uses build_manifest (reads json only, signs nothing).

    uv run python tests/test_certify_gate.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.certify import build_manifest, issue
from tools.challenge import ChallengeUnavailable

# A minimal run dir: both issue() (via the gate) and build_manifest read only these two.
BEHAVIORAL = {"overall": {"neutral_rate": 0.0, "incentivized_rate": 0.3167}}
VALIDATION = {"defensible_vs_truth_agreement": 0.8827,
              "suppression_detection": {"recall": 1.0}}


def _run_dir() -> Path:
    d = Path(tempfile.mkdtemp())
    (d / "behavioral.json").write_text(json.dumps(BEHAVIORAL))
    (d / "validation.json").write_text(json.dumps(VALIDATION))
    return d


def test_independent_is_refused(_):
    # issue() gates before touching the signing key or writing a cert, so this is safe
    # even with no private key present (as in CI, where it is gitignored).
    try:
        issue(_run_dir(), "Acme Bank", "vendor-triage-v3", "independent")
    except ChallengeUnavailable:
        return  # gated as intended — the OSS repo cannot mint the paid tier
    raise AssertionError("`--level independent` was self-issued; the paid tier is not gated")


def test_self_tested_is_unaffected(_):
    # The weak tier's manifest still builds and stamps self-tested (no signing/keys/writes).
    m = build_manifest(_run_dir(), "Acme Bank", "vendor-triage-v3", "self-tested",
                       issued_at="2026-06-26T00:00:00+00:00", valid_days=90)
    assert m["assurance_level"] == "self-tested"
    assert m["schema"] == "cupel/self-cert/v1"


def main() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t(None)
        print(f"  ok  {t.__name__}")
    print(f"[certify gate tests] {len(tests)} passed")


if __name__ == "__main__":
    main()
