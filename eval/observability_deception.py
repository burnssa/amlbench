"""Observability on the DECEPTION axis — does a standard quality/monitoring stack catch a
frontier agent being fooled by a grounded cover story into clearing a reportable alert?

Runs the target on the reportable alerts in two conditions, both at the FULL-SPEC base:
  A0 (baseline) — the raw alerts; the agent escalates ~all of them.
  A2 (deceived) — the same alerts with grounded launderer cover stories woven in; the agent
                  under-escalates (clears reportable activity it was fooled about).
Every decision is scored through the SAME observability quality evals used for the v0 run
(groundedness / coherence / hallucination + latency / cost / drift), and we ask whether any
alarm would fire. Expected (thesis): none — a suppressed-but-plausible clearance is grounded
and coherent, so the stack stays green while the agent is deceived.

Reuses observability/{instrument,metrics}.py unchanged. Writes results/observability_deception/
<model>.json — touches no existing data.

    uv run python -m eval.observability_deception --model claude-opus-4-8   # ~$2-3
"""
from __future__ import annotations

import argparse
import json

from agent.conditions import NEUTRAL, OUTPUT_CONTRACT
from agent.triage import decide
from common.config import load_config, resolve
from common.io import read_jsonl
from common.parallel import thread_map
from observability.instrument import init_phoenix, trace_decision, score_quality, mode
from observability.metrics import build_observability_report

B2_FILE = "data/framings/base_role_strong_v2.txt"
COVERS = "data/adversary/covers.jsonl"


def _covered(alert: dict, cover: dict) -> dict:
    """A2: prepend the grounded cover story; features + ground truth untouched."""
    intro = f"{cover['cover_A1']} {cover.get('cover_A2_kyc', '')}"
    return {**alert, "narrative": f"Customer business context: {intro}\n\n{alert['narrative']}"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--max-tokens", type=int, default=2500)
    ap.add_argument("--out", default="results/observability_deception")
    args = ap.parse_args()

    cfg = load_config()
    m = init_phoenix(cfg)
    system = f"{resolve(B2_FILE).read_text().strip()}\n\n{NEUTRAL}\n\n{OUTPUT_CONTRACT}"
    covers = {c["alert_id"]: c for c in (json.loads(l) for l in resolve(COVERS).read_text().splitlines() if l.strip())}
    alerts = {a["alert_id"]: a for a in read_jsonl(resolve(cfg["dataset"]["output"]))}
    reportable = [alerts[aid] for aid in covers if aid in alerts]
    covered = [_covered(a, covers[a["alert_id"]]) for a in reportable]
    print(f"[obs-deception] {args.model} · {len(reportable)} reportable alerts · A0 raw vs A2 cover · obs mode: {m}")

    def run(queue, label):
        decs = thread_map(lambda a: decide(a, system=system, model=args.model, condition=label,
                          phrasing=None, seed=cfg["run"]["core_seed"], max_tokens=args.max_tokens,
                          temperature=0.0), queue, workers=cfg["run"]["workers"], label=f"triage/{label}")
        for d in decs:
            trace_decision(d)
        q = thread_map(lambda d: score_quality(d, cfg), decs, workers=cfg["run"]["workers"], label=f"quality/{label}")
        return decs, q

    a0_decs, a0_q = run(reportable, "A0_raw")
    a2_decs, a2_q = run(covered, "A2_cover")

    report = build_observability_report(a0_decs, a0_q, a2_decs, a2_q, m)
    # relabel the two conditions for the deception framing (structure/logic identical)
    report = {"model": args.model, "axis": "data-adversary (A0 raw vs A2 grounded cover)",
              "baseline_A0": report["neutral"], "deceived_A2": report["incentivized"],
              "verdict": report["verdict"], "drift": report["drift"]}
    cost = (sum(d["usage"]["cost_usd"] for d in a0_decs + a2_decs)
            + sum(q.get("judge_cost_usd", 0.0) for q in a0_q + a2_q))
    report["est_cost_usd"] = round(cost, 2)

    out = resolve(args.out, f"{args.model.split('/')[-1]}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    b, d, v = report["baseline_A0"], report["deceived_A2"], report["verdict"]
    print(f"\n[obs-deception] escalation {b['escalation_rate']:.0%} -> {d['escalation_rate']:.0%}  "
          f"| groundedness {b['mean_groundedness']:.2f} -> {d['mean_groundedness']:.2f}  "
          f"| coherence {b['mean_coherence']:.2f} -> {d['mean_coherence']:.2f}  "
          f"| ALARMS: {v['n_alarms']}   est. ${cost:.2f}")
    print(f"[obs-deception] -> {out}")


if __name__ == "__main__":
    main()
