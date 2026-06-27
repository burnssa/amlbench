"""cert_request.json — the anonymized, aggregate-only artifact a run offers up so a
customer can request a certificate, after inspecting exactly what would be shared.

Design points:
  * Records what makes the number meaningful, not just the number: battery hash + kind,
    git commit, model + provider, condition coverage, and the figures (one decimal),
    behind a `schema` version so the format can evolve.
  * States WHICH battery it scored — `open-practice` (self-scored, gameable: the weak
    tier the limitation names) vs `held-out-challenge` (the stronger tier). The
    self-cert gap is thus encoded in the artifact itself; a cert can never overclaim.
  * Is aggregate-only — rates, counts, hashes, identifiers; NO raw decisions, rationales,
    per-alert rows, or PII. `assert_aggregate_only()` enforces this (tests/test_cert_request.py).
  * Honors the promise literally: emit_cert_request() prints the full JSON inline under
    claims.CERT_REQUEST_PROMISE, so the page's "inspect before it leaves" claim is true.
"""
from __future__ import annotations

import json
import math
import subprocess
from datetime import datetime, timezone

from common.claims import AGGREGATE_ONLY, CERT_REQUEST_PROMISE, SELF_CERT_DISCLAIMER, SELF_CERT_GAP
from common.config import resolve
from tools.certify import _battery_hash

SCHEMA = "cupel/cert-request/v1"
BATTERY_KINDS = ("open-practice", "held-out-challenge")

# Keys that would indicate per-alert / raw / identifying content leaked into the request.
_FORBIDDEN_KEYS = {
    "alert_id", "rationale", "reasoning", "narrative", "decision", "decisions",
    "features", "transactions", "cash_transactions", "focal_account", "pii",
}


def _pct1(x) -> float | None:
    """One-decimal percentage, or None for missing/NaN."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(x * 100, 1)


def _git_short() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def assert_aggregate_only(req: dict) -> None:
    """Raise if the request carries any per-alert/raw/PII content. Enforced, not promised.

    Rejects (a) any forbidden key anywhere, and (b) any list element that is itself a
    dict or list — i.e. a per-row record. Scalars and string lists (e.g. conditions) pass.
    """
    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                if str(k).lower() in _FORBIDDEN_KEYS:
                    raise AssertionError(f"cert_request not aggregate-only: forbidden key {k!r} at {path}")
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                if isinstance(v, (dict, list)):
                    raise AssertionError(
                        f"cert_request not aggregate-only: nested collection at {path}[{i}] "
                        "(looks like per-row data)")
                walk(v, f"{path}[{i}]")

    walk(req, "$")


def build_cert_request(*, cfg, run_meta, conditions, provider, n_decisions, n_reportable,
                       neutral_rate, incent_rate=None, agreement=None, detection_recall=None,
                       battery_kind="open-practice", battery_version="practice",
                       git_commit=None, generated_at=None) -> dict:
    if battery_kind not in BATTERY_KINDS:
        raise ValueError(f"battery_kind must be one of {BATTERY_KINDS}, got {battery_kind!r}")
    ne, ie = _pct1(neutral_rate), _pct1(incent_rate)
    metrics = {
        "under_escalation_neutral_pct": ne,
        "under_escalation_incentivized_pct": ie,
        "susceptibility_delta_pct": (round(ie - ne, 1) if (ne is not None and ie is not None) else None),
        "evaluator_vs_truth_agreement_pct": _pct1(agreement),
        "under_escalation_detection_recall_pct": _pct1(detection_recall),
        "n_decisions": int(n_decisions),
        "n_reportable_alerts": int(n_reportable),
    }
    req = {
        "schema": SCHEMA,
        "generated_at": generated_at or datetime.now(timezone.utc).date().isoformat(),
        "git_commit": git_commit or _git_short(),
        "battery": {
            "kind": battery_kind,  # open-practice = self-scored & gameable; held-out-challenge = stronger
            "version": battery_version,  # 'practice' or a rotated id e.g. 'challenge-v3' (v3 != v7)
            "hash": _battery_hash(),
            "n_alerts": cfg["dataset"]["n_alerts"],
            "substrate": cfg["dataset"]["substrate"],
        },
        "agent": {
            "descriptor": run_meta.get("agent_descriptor") or run_meta.get("agent"),
            "model": run_meta.get("agent"),
            "provider": provider,
        },
        "evaluator": cfg["evaluator"]["model"],
        "conditions": list(conditions),
        "assurance_level": "self-tested" if battery_kind == "open-practice" else "self-tested-challenge",
        "metrics": metrics,
        "disclaimer": SELF_CERT_DISCLAIMER,
        "self_cert_gap": SELF_CERT_GAP,
        "guarantee": AGGREGATE_ONLY,
    }
    assert_aggregate_only(req)  # self-check before anything is written or printed
    return req


def emit_cert_request(req: dict, out_path: str, *, print_inline: bool = True) -> str:
    """Write the request and (by default) print it inline so the user sees exactly what
    would be shared before requesting a certificate."""
    assert_aggregate_only(req)
    path = resolve(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(req, indent=2, ensure_ascii=False)  # keep — and punctuation human-readable
    path.write_text(text + "\n")
    if print_inline:
        print(f"\n[cert] {CERT_REQUEST_PROMISE}")
        print(text)
        print(f"[cert] saved -> {path}")
    return str(path)


def write_cert_request(*, out_path, print_inline=True, **kwargs) -> str:
    """Build + emit in one call (the convenience used by run.py / rerender / ws2)."""
    return emit_cert_request(build_cert_request(**kwargs), out_path, print_inline=print_inline)
