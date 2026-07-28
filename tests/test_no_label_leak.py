"""Regression guard: no agent-visible string may encode the ground-truth label.

Covers the leak class found 2026-07: typology-named alert IDs (STRUCTURING_*,
NORM-, BENIGN_*) embedded verbatim in narratives/prompts/exports. Asserts every
agent-visible surface — the standard triage prompt, the narrative (what
cover-weaving preserves), the interp ledger presentation, and the BYO battery
export rows — is free of typology names, benign-marker prefixes, gt_* values,
and the internal 'subtle' flag. Runs offline; part of scripts/verify.sh.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.byo import battery_prompt  # noqa: E402
from agent.triage import present_alert  # noqa: E402
from common.config import load_config, resolve  # noqa: E402
from interp.presentation import present_alert_ledger  # noqa: E402

# Forbidden as case-insensitive substrings of any agent-visible string. Plain
# words like "payroll" (a legitimate KYC profile) are NOT forbidden — only the
# label-bearing tokens are.
FORBIDDEN = [
    "structuring", "passthrough", "pass_through", "layering", "fan_out", "fan_in",
    "dispersion", "norm-", "benign_", "subtle",
    "should_escalate", "should_clear", "gt_typology", "is_sar",
]


def _violations(text: str) -> list[str]:
    low = text.lower()
    return [w for w in FORBIDDEN if w in low]


def main() -> None:
    cfg = load_config()
    alerts = [json.loads(l) for l in
              resolve(cfg["dataset"]["output"]).read_text().splitlines() if l.strip()]
    assert alerts, "no alerts — run data.build first"
    assert all("display_id" in a for a in alerts), "battery predates v0.2 opaque IDs"
    assert not any(re.search(r"[A-Z][A-Z0-9_]+-\d{4}", a["display_id"]) for a in alerts)

    bad = []
    for a in alerts:
        for surface, text in (
            ("present_alert", present_alert(a)),
            ("narrative", a["narrative"]),
            ("ledger", present_alert_ledger(a)),
            ("byo_export_row", json.dumps(
                {"alert_id": a.get("display_id", a["alert_id"]),
                 "prompt": battery_prompt(a)})),
        ):
            hits = _violations(text)
            if hits:
                bad.append((a["alert_id"], surface, hits))
    if bad:
        for aid, surface, hits in bad[:10]:
            print(f"LEAK {aid} via {surface}: {hits}")
        raise AssertionError(f"{len(bad)} agent-visible strings leak label tokens")

    probe = Path(__file__).resolve().parent.parent / "interp" / "data" / "alerts_probe.jsonl"
    if probe.exists():
        prows = [json.loads(l) for l in probe.read_text().splitlines() if l.strip()]
        pbad = [(a["alert_id"], _violations(present_alert_ledger(a))) for a in prows
                if _violations(present_alert_ledger(a))]
        assert not pbad, f"probe-set leaks: {pbad[:5]}"
        print(f"[leak test] probe set clean ({len(prows)} alerts)")

    print(f"[leak test] OK — {len(alerts)} alerts x 4 surfaces, no label tokens")


if __name__ == "__main__":
    main()
