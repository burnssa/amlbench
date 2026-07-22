"""Build the PRIVATE probe-training alert set for the interp experiment.

Loops fresh seeds through the deterministic pipeline (amlsim substrate ->
build_alerts -> rule labels), aggregates across seeds until the reportable /
benign targets are met, and writes to the gitignored interp/data/ — this set
doubles as a private holdout for client engagements and is NEVER committed.

Published seeds (11 canonical, 23, 42) are excluded so the probe set shares no
alert with any public number. Class is assigned by the deterministic rule label
(ground_truth.label), not the AMLSim is_sar flag; the rare normal-traffic window
that trips a rule counts as reportable. Benign hard negatives (payroll/vendor
decoys) are all kept; quiet normals fill the remainder. An 80/20 train/val
split is stratified by (label, typology) so probes can hold typologies constant.

    uv run python interp/build_probe_set.py                 # 500 + 500 default
    uv run python interp/build_probe_set.py --n-report 200 --n-benign 200 --dry
"""
from __future__ import annotations

import argparse
import hashlib
import random
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from common.config import load_config  # noqa: E402
from common.io import write_json, write_jsonl  # noqa: E402
from data import amlsim, rules  # noqa: E402
from data.build import build_alerts  # noqa: E402

PUBLISHED_SEEDS = {11, 23, 42}
BENIGN_DECOYS = {"benign_payroll", "benign_vendor"}
SPLIT_SEED = 1234


def _dedupe_key(alert: dict) -> str:
    # Narrative minus its embedded alert id — catches identical windows across seeds.
    text = alert["narrative"].replace(alert.get("orig_alert_id", alert["alert_id"]), "")
    return hashlib.sha256(text.encode()).hexdigest()


def _assign_splits(alerts: list[dict], val_frac: float) -> None:
    strata = defaultdict(list)
    for a in alerts:
        strata[(a["ground_truth"]["label"], a["gt_typology"])].append(a)
    rng = random.Random(SPLIT_SEED)
    for group in strata.values():
        rng.shuffle(group)
        n_val = max(1, round(len(group) * val_frac)) if len(group) > 1 else 0
        for i, a in enumerate(group):
            a["split"] = "val" if i < n_val else "train"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--n-report", type=int, default=500)
    ap.add_argument("--n-benign", type=int, default=500)
    ap.add_argument("--start-seed", type=int, default=101)
    ap.add_argument("--max-seeds", type=int, default=40)
    ap.add_argument("--val-frac", type=float, default=0.2)
    ap.add_argument("--config", default=None)
    ap.add_argument("--out-dir", default=str(REPO_ROOT / "interp" / "data"))
    ap.add_argument("--dry", action="store_true", help="report counts, write nothing")
    args = ap.parse_args()

    cfg = load_config(args.config)
    seen: set[str] = set()
    reportable: list[dict] = []
    decoys: list[dict] = []
    normals: list[dict] = []
    seeds_used: list[int] = []

    seed = args.start_seed
    while len(reportable) < args.n_report and len(seeds_used) < args.max_seeds:
        if seed in PUBLISHED_SEEDS:
            seed += 1
            continue
        sub = amlsim.generate_substrate(cfg, seed)
        for a in build_alerts(cfg, sub):
            a["orig_alert_id"] = a["alert_id"]
            a["alert_id"] = f"S{seed}-{a['alert_id']}"
            a["seed"] = seed
            key = _dedupe_key(a)
            if key in seen:
                continue
            seen.add(key)
            if a["ground_truth"]["label"] == rules.ESCALATE:
                reportable.append(a)
            elif a["gt_typology"] in BENIGN_DECOYS:
                decoys.append(a)
            else:
                normals.append(a)
        seeds_used.append(seed)
        print(f"[probe-set] seed={seed} cum: reportable={len(reportable)} "
              f"decoy={len(decoys)} normal={len(normals)}")
        seed += 1

    if len(reportable) < args.n_report:
        raise SystemExit(f"only {len(reportable)} reportable after {len(seeds_used)} seeds")

    rng = random.Random(SPLIT_SEED)
    reportable = reportable[: args.n_report]
    # Benign: every busy-looking decoy first (hard negatives), quiet normals fill.
    if len(decoys) >= args.n_benign:
        rng.shuffle(decoys)
        benign = decoys[: args.n_benign]
    else:
        rng.shuffle(normals)
        benign = decoys + normals[: args.n_benign - len(decoys)]

    alerts = reportable + benign
    _assign_splits(alerts, args.val_frac)

    by_typ = defaultdict(lambda: defaultdict(int))
    for a in alerts:
        by_typ[a["gt_typology"]][a["split"]] += 1
    summary = {
        "n_reportable": len(reportable),
        "n_benign": len(benign),
        "n_benign_decoy": sum(1 for a in benign if a["gt_typology"] in BENIGN_DECOYS),
        "seeds_used": seeds_used,
        "published_seeds_excluded": sorted(PUBLISHED_SEEDS),
        "val_frac": args.val_frac,
        "by_typology": {k: dict(v) for k, v in sorted(by_typ.items())},
    }
    for k, v in summary.items():
        print(f"  {k}: {v}")

    if args.dry:
        print("[probe-set] --dry: nothing written")
        return
    out_dir = Path(args.out_dir)
    n = write_jsonl(out_dir / "alerts_probe.jsonl", alerts)
    write_json(out_dir / "alerts_probe_summary.json", summary)
    print(f"[probe-set] wrote {n} alerts -> {out_dir / 'alerts_probe.jsonl'} (PRIVATE, gitignored)")


if __name__ == "__main__":
    main()
