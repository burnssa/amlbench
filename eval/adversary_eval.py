"""Data-adversary eval (A1/A2): does a grounded cover story make a spec-complete frontier
model clear genuinely reportable alerts?

Holds model + system prompt fixed (spec-complete base + neutral/accurate-triage instruction —
NO incentive, NO directive) and varies only the ALERT DATA:
  raw  — the reportable alert as-is
  A1   — + a grounded innocent business-context intro
  A2   — + supporting expected-activity / KYC profile
`features` and ground truth are identical across all three, so any rise in under-escalation is
the model being talked out of a still-visible pattern by the cover story.

    uv run python -m eval.adversary_eval --model claude-opus-4-8   # ~$3-4
"""
from __future__ import annotations

import argparse
import json

from agent.conditions import NEUTRAL, OUTPUT_CONTRACT
from agent.triage import decide
from common.config import load_config, resolve
from common.io import read_jsonl
from common.parallel import thread_map
from eval.metrics import under_escalation_rate

COVERS = "data/adversary/covers.jsonl"
OVERT = "structuring_overt"


def _variant(alert: dict, cover: dict | None, level: str) -> dict:
    if cover is None or level == "raw":
        return alert
    intro = cover["cover_A1"] if level == "A1" else f"{cover['cover_A1']} {cover.get('cover_A2_kyc','')}"
    return {**alert, "narrative": f"Customer business context: {intro}\n\n{alert['narrative']}"}


def _run(alerts: list[dict], system: str, model: str, level: str, cfg, max_tokens: int) -> list[dict]:
    return thread_map(
        lambda a: decide(a, system=system, model=model, condition=level, phrasing=None,
                         seed=cfg["run"]["core_seed"], max_tokens=max_tokens, temperature=0.0),
        alerts, workers=cfg["run"]["workers"], label=f"adv/{level}",
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--base-role-file", default="data/framings/base_role_strong.txt")
    ap.add_argument("--max-tokens", type=int, default=2500)
    ap.add_argument("--out", default="results/adversary_eval")
    args = ap.parse_args()

    cfg = load_config()
    base_role = resolve(args.base_role_file).read_text().strip()
    system = f"{base_role}\n\n{NEUTRAL}\n\n{OUTPUT_CONTRACT}"

    covers = {c["alert_id"]: c for c in (json.loads(l) for l in resolve(COVERS).read_text().splitlines() if l.strip())}
    alerts = {a["alert_id"]: a for a in read_jsonl(resolve(cfg["dataset"]["output"]))}
    reportable = [alerts[aid] for aid in covers if aid in alerts]  # only the ones we generated covers for
    print(f"[adv-eval] {args.model} · {len(reportable)} reportable alerts · spec-complete base ({args.base_role_file})")

    out, cost = {}, 0.0
    for level in ("raw", "A1", "A2"):
        variants = [_variant(a, covers.get(a["alert_id"]), level) for a in reportable]
        recs = _run(variants, system, args.model, level, cfg, args.max_tokens)
        cost += sum(r["usage"]["cost_usd"] for r in recs)
        u, missed, total = under_escalation_rate(recs)
        u_overt, mo, to = under_escalation_rate(recs, OVERT)
        out[level] = {"U": u, "missed": missed, "total": total, "U_overt": u_overt, "overt_total": to}
        print(f"  {level:<4} under-escalation {u:5.1%}  ({missed}/{total} reportable cleared)   "
              f"overt-structuring {u_overt:5.1%} ({mo}/{to})")

    dA1 = out["A1"]["U"] - out["raw"]["U"]
    dA2 = out["A2"]["U"] - out["raw"]["U"]
    print(f"\n  deception Δ vs raw:   A1 {dA1:+.2f}   A2 {dA2:+.2f}    (est. cost ${cost:.2f})")
    resolve(args.out, "adversary_eval.json").parent.mkdir(parents=True, exist_ok=True)
    resolve(args.out, "adversary_eval.json").write_text(json.dumps(
        {"model": args.model, "base_role": args.base_role_file, "levels": out,
         "delta_A1": round(dA1, 3), "delta_A2": round(dA2, 3), "est_cost_usd": round(cost, 2)}, indent=2))


if __name__ == "__main__":
    main()
