"""cert_request.json is aggregate-only — proven, not promised (like netguard's zero egress).

    uv run python tests/test_cert_request.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from finding.cert_request import BATTERY_KINDS, SCHEMA, assert_aggregate_only, build_cert_request

CFG = {"dataset": {"n_alerts": 240, "substrate": "amlsim_port"}, "evaluator": {"model": "claude-opus-4-8"}}
RUN_META = {"mode": "core", "agent": "claude-sonnet-4-6"}


def _req():
    return build_cert_request(
        cfg=CFG, run_meta=RUN_META, conditions=["neutral", "incentivized"], provider="anthropic",
        n_decisions=120, n_reportable=60, neutral_rate=0.0, incent_rate=0.3167,
        agreement=0.8827, detection_recall=1.0, generated_at="2026-06-26", git_commit="testsha")


def test_real_request_is_aggregate_only(_):
    assert_aggregate_only(_req())  # build_cert_request also self-checks; this is belt-and-suspenders


def test_schema_and_battery_kind_present(_):
    r = _req()
    assert r["schema"] == SCHEMA
    assert r["battery"]["kind"] in BATTERY_KINDS
    assert r["battery"]["hash"].startswith("sha256:")
    for k in ("git_commit", "agent", "evaluator", "conditions", "metrics", "self_cert_gap", "guarantee"):
        assert k in r, f"missing top-level key {k}"


def test_figures_are_one_decimal(_):
    m = _req()["metrics"]
    assert m["under_escalation_neutral_pct"] == 0.0
    assert m["under_escalation_incentivized_pct"] == 31.7
    assert m["susceptibility_delta_pct"] == 31.7
    assert m["evaluator_vs_truth_agreement_pct"] == 88.3
    assert m["under_escalation_detection_recall_pct"] == 100.0


def test_forbidden_key_is_rejected(_):
    r = _req()
    r["metrics"]["rationale"] = "an agent rationale leaked in"
    try:
        assert_aggregate_only(r)
    except AssertionError:
        return
    raise AssertionError("forbidden key 'rationale' was not caught")


def test_per_alert_rows_are_rejected(_):
    r = _req()
    r["rows"] = [{"x": 1}]  # a list of dicts = per-row data
    try:
        assert_aggregate_only(r)
    except AssertionError:
        return
    raise AssertionError("per-row list was not caught")


def main() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t(None)
        print(f"  ok  {t.__name__}")
    print(f"[cert_request tests] {len(tests)} passed")


if __name__ == "__main__":
    main()
