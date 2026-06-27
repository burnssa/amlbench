"""Cheap inducibility probe (Claim 1 only): agent-only, no evaluator/Phoenix.

Runs the triage agent across `neutral` + a ladder of incentive phrasings of
increasing strength, on an escalate-heavy subset, and reports the under-escalation
(suppression) rate per phrasing — overall and for the structuring target class —
plus over-escalation. The point is to see, honestly and across the whole ladder,
whether (and where) a realistic production incentive induces the shortcut, before
committing to a full Opus-evaluator run.

    uv run python -m eval.probe                 # all phrasings, default subset
    uv run python -m eval.probe --clears 24 --workers 8
"""
from __future__ import annotations

import argparse
import random
from concurrent.futures import ThreadPoolExecutor

from common.config import load_config, resolve
from common.io import read_jsonl, write_json, write_jsonl
from common.llm import api_key_available
from agent.triage import triage_one
from agent.conditions import incentive_phrasings
from eval import metrics as M

ESCALATE = "SHOULD_ESCALATE"


def build_probe_set(alerts: list[dict], n_clears: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    esc = [a for a in alerts if a["ground_truth"]["label"] == ESCALATE]
    clears = [a for a in alerts if a["ground_truth"]["label"] != ESCALATE]
    pick = esc + rng.sample(clears, min(n_clears, len(clears)))
    rng.shuffle(pick)
    return pick


def run_cell(alerts, condition, phrasing, cfg, seed, workers) -> list[dict]:
    def work(a):
        return triage_one(a, condition, phrasing, cfg, seed)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(work, alerts))


def summarize_cell(decs: list[dict], typologies: list[str]) -> dict:
    ue, miss, tot = M.under_escalation_rate(decs)
    oer, over, ctot = M.false_escalation_rate(decs)
    per = {}
    for t in typologies:
        r, m, n = M.under_escalation_rate(decs, t)
        per[t] = {"rate": round(r, 4), "missed": m, "total": n}
    return {
        "under_escalation": round(ue, 4), "missed": miss, "escalate_truth": tot,
        "over_escalation": round(oer, 4), "over": over, "clear_truth": ctot,
        "per_typology": per,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clears", type=int, default=24)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()

    cfg = load_config()
    if not api_key_available():
        raise SystemExit("ANTHROPIC_API_KEY not set (put it in .env).")
    seed = args.seed if args.seed is not None else cfg["run"]["core_seed"]

    alerts = list(read_jsonl(resolve(cfg["dataset"]["output"])))
    probe = build_probe_set(alerts, args.clears, seed)
    n_esc = sum(1 for a in probe if a["ground_truth"]["label"] == ESCALATE)
    n_struct = sum(1 for a in probe if a["gt_typology"] == "structuring")
    print(f"[probe] {len(probe)} alerts ({n_esc} escalate-truth incl. {n_struct} structuring) "
          f"x {1 + len(incentive_phrasings(cfg))} conditions, seed={seed}")

    typologies = sorted({a["gt_typology"] for a in probe
                         if a["ground_truth"]["label"] == ESCALATE})
    cells = [("neutral", None)] + [("incentivized", p) for p in incentive_phrasings(cfg)]
    results = {}
    all_decs = []
    for cond, ph in cells:
        label = ph or "neutral"
        print(f"  [probe] running {label}…")
        decs = run_cell(probe, cond, ph, cfg, seed, args.workers)
        all_decs += decs
        results[label] = summarize_cell(decs, typologies)

    out_dir = resolve("results", "runs", "probe")
    write_jsonl(out_dir / "decisions.jsonl", all_decs)
    write_json(out_dir / "probe.json", results)

    # Console: overall ladder + per-typology suppression matrix (cleared/total).
    base = results["neutral"]["under_escalation"]
    print("\n" + "=" * 78)
    print(f"{'phrasing':<20}{'under-esc':>11}{'over-esc':>10}{'Δ vs neutral':>14}")
    print("-" * 78)
    for label, r in results.items():
        d = "" if label == "neutral" else f"+{r['under_escalation'] - base:.1%}"
        print(f"{label:<20}{r['under_escalation']:>10.1%}{r['over_escalation']:>10.1%}{d:>14}")
    print("\nSuppression by typology (cleared / reportable):")
    short = {t: t.replace("structuring_", "str_")[:13] for t in typologies}
    print(f"{'phrasing':<20}" + "".join(f"{short[t]:>15}" for t in typologies))
    for label, r in results.items():
        row = f"{label:<20}"
        for t in typologies:
            p = r["per_typology"][t]
            row += f"{(str(p['missed']) + '/' + str(p['total'])):>15}"
        print(row)
    print("=" * 78)
    total = sum(d["usage"]["cost_usd"] for d in all_decs)
    print(f"agent calls: {len(all_decs)}  est. spend: ${total:.2f}  -> {out_dir}/probe.json")


if __name__ == "__main__":
    main()
