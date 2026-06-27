"""Air-gapped self-cert: the ENTIRE practice path completes with all network blocked.

Backs the landing page's "run it air-gapped" claim end-to-end, not just on one function:
    data.build (substrate -> labeled alerts) -> export battery -> logreplay ingest
    -> behavioral under-escalation -> cert_request
all under common.netguard.no_network(). If any step reaches the network the guard raises.

    uv run python tests/test_airgapped_selfcert.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.byo import export_battery, load_logreplay_decisions
from common.config import load_config
from common.netguard import no_network
from data import amlsim
from data import build as databuild
from eval import metrics as beh_metrics
from finding.cert_request import assert_aggregate_only, build_cert_request

SAMPLE = "samples/sample_decisions.csv"


def main() -> None:
    cfg = load_config()
    tmp = Path(tempfile.mkdtemp())

    # Everything below must run with zero outbound network.
    with no_network():
        # 1. data.build: substrate -> labeled alerts (offline, deterministic)
        sub = amlsim.generate_substrate(cfg, cfg["run"]["core_seed"])
        alerts = databuild.build_alerts(cfg, sub)
        battery = {a["alert_id"]: a for a in alerts}

        # 2. export the practice battery (prompts only, no labels) + manifest
        export_battery(alerts, tmp / "battery.jsonl")
        assert (tmp / "battery_manifest.json").exists(), "export did not write the practice manifest"

        # 3. logreplay ingest of a decisions CSV keyed to the battery
        records = load_logreplay_decisions(SAMPLE, battery)
        assert records, "no records ingested"

        # 4. behavioral under-escalation (offline scoring against ground truth)
        neutral = [r for r in records if r["condition"] == "neutral"]
        incent = [r for r in records if r["condition"] == "incentivized"]
        nr, _, _ = beh_metrics.under_escalation_rate(neutral)
        ir, _, it = beh_metrics.under_escalation_rate(incent)

        # 5. cert_request (the artifact the user would share)
        req = build_cert_request(
            cfg=cfg, run_meta={"mode": "airgap-test", "agent": "logreplay"},
            conditions=["neutral", "incentivized"], provider="logreplay (offline)",
            n_decisions=len(records), n_reportable=it, neutral_rate=nr, incent_rate=ir)
        assert_aggregate_only(req)
        assert req["schema"] == "cupel/cert-request/v1"
        assert req["battery"]["kind"] == "open-practice"

    print(f"[airgapped] OK — full self-cert path ran with network blocked "
          f"(under-escalation {nr:.1%} -> {ir:.1%}, {len(records)} decisions)")


if __name__ == "__main__":
    main()
