"""No API-key value is ever written to an emitted artifact.

"Env-only" is necessary but the real promise is "never written anywhere." This proves it
two ways: (A) a sentinel key set in the environment does not appear in a freshly built
cert_request, and (B) no key-shaped secret appears in any committed emitted artifact
(reports, ledgers, attestations, cert_requests).

    uv run python tests/test_no_secret_leak.py
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finding.cert_request import build_cert_request

# Key-shaped secrets (provider tokens / AWS) — independent of whatever is in the env.
KEY_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-proj-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\br8_[A-Za-z0-9]{20,}\b"),  # Replicate tokens
]
SENTINEL = "sk-ant-SENTINELdonotleak0123456789"
KEY_ENV_VARS = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "REPLICATE_API_TOKEN",
                "REPLICATE_API_KEY", "TOGETHER_API_KEY", "FIREWORKS_API_KEY",
                "OPENROUTER_API_KEY", "GROQ_API_KEY", "XAI_API_KEY",
                "AMLBENCH_AGENT_API_KEY", "CUPEL_AGENT_API_KEY"]

CFG = {"dataset": {"n_alerts": 240, "substrate": "amlsim_port"}, "evaluator": {"model": "claude-opus-4-8"}}


def test_sentinel_key_not_in_cert_request(_):
    os.environ["ANTHROPIC_API_KEY"] = SENTINEL
    os.environ["AMLBENCH_AGENT_API_KEY"] = SENTINEL
    req = build_cert_request(
        cfg=CFG, run_meta={"mode": "leak-test", "agent": "claude-sonnet-4-6"},
        conditions=["neutral", "incentivized"], provider="anthropic", n_decisions=10,
        n_reportable=5, neutral_rate=0.0, incent_rate=0.3, agreement=0.88, detection_recall=1.0,
        git_commit="testsha", generated_at="2026-06-26")
    blob = json.dumps(req)
    assert SENTINEL not in blob, "sentinel API key leaked into cert_request"


def test_no_key_shaped_secret_in_committed_artifacts(_):
    root = Path(__file__).resolve().parent.parent
    real_secrets = {os.environ.get(v) for v in KEY_ENV_VARS} - {None, "", SENTINEL}
    files: list[str] = []
    for pat in ("results/**/*.md", "results/**/*.json", "results/**/*.jsonl"):
        files += glob.glob(str(root / pat), recursive=True)
    scanned = 0
    for f in files:
        text = Path(f).read_text(errors="ignore")
        scanned += 1
        for rx in KEY_PATTERNS:
            m = rx.search(text)
            assert not m, f"possible key in {f}: {m.group()[:10]}…"
        for secret in real_secrets:
            assert secret not in text, f"a real env key value appears in {f}"
    assert scanned > 0, "no artifacts scanned — check the glob"


def main() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t(None)
        print(f"  ok  {t.__name__}")
    print(f"[no-secret-leak] {len(tests)} passed")


if __name__ == "__main__":
    main()
