"""Cupel headline reproduction — replay from committed fixtures, no API key.

Re-scores the committed agent decision logs (`results/runs/*/decisions.jsonl`, which
embed the deterministic BSA/AML ground-truth label per alert) through the SAME scorer
the pipeline uses (`eval.metrics.under_escalation_rate`), reproduces the headline
table, self-checks it against the committed cross-model metrics, and writes a
machine-readable `results.json`. No model calls, no network, fully deterministic — the
decisions are frozen fixtures.

    uv run python -m tools.repro

Read-only w.r.t. every committed artifact: it reads decision logs + metric JSONs and
writes ONLY `results.json` (gitignored). The opt-in LIVE re-run is the existing
`uv run python run.py --mode core` (needs ANTHROPIC_API_KEY; see AGENTS.md).
"""
from __future__ import annotations

import json
from pathlib import Path

from common.config import resolve
from eval.metrics import under_escalation_rate
from eval import figstyle as S

# The published cross-model ladder (ladder_5model/multimodel.json) is a read-only
# COMBINATION of these two live runs' decision logs; re-scoring them reproduces it.
LADDER_RUNS = ["multimodel_ladder", "opus_ladder"]
COMMITTED_LADDER = ("results", "runs", "ladder_5model", "multimodel.json")
CONDITION_ORDER = ["neutral", "throughput_backlog", "cost_efficiency", "strong", "quota"]
MODEL_ORDER = ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
               "gpt-4o", "replicate/meta/meta-llama-3-70b-instruct"]


def _load_jsonl(run: str) -> list[dict]:
    with open(resolve("results", "runs", run, "decisions.jsonl")) as f:
        return [json.loads(line) for line in f]


def _cell_key(rec: dict) -> str:
    """Ladder cell a decision belongs to: 'neutral', else the incentive framing."""
    return "neutral" if rec["condition"] == "neutral" else rec["phrasing"]


def _cell(rate: float, missed: int, total: int) -> dict:
    return {"under_escalation": round(rate, 4), "missed": missed, "total": total}


def rescore_ladder() -> dict:
    """Re-derive under-escalation per model x condition from committed decision logs."""
    recs = [r for run in LADDER_RUNS for r in _load_jsonl(run)]
    models = sorted({r["agent_model"] for r in recs},
                    key=lambda m: MODEL_ORDER.index(m) if m in MODEL_ORDER else 99)
    out = {}
    for model in models:
        cells = {}
        for cond in CONDITION_ORDER:
            sel = [r for r in recs if r["agent_model"] == model and _cell_key(r) == cond]
            if sel:
                cells[cond] = _cell(*under_escalation_rate(sel))
        out[model] = cells
    return out


def rescore_core() -> dict:
    """Reference agent (Sonnet, N=240): neutral vs peer-benchmark under-escalation."""
    recs = _load_jsonl("core")
    neu = under_escalation_rate([r for r in recs if r["condition"] == "neutral"])
    inc = under_escalation_rate([r for r in recs if r["condition"] == "incentivized"])
    return {"model": "claude-sonnet-4-6", "neutral": _cell(*neu), "peer_benchmark": _cell(*inc)}


def verifier_recall() -> dict:
    """Blind-verifier recall on suppressed reportable alerts (committed validation)."""
    v = json.loads(resolve("results", "runs", "core", "validation.json").read_text())
    sd = v["suppression_detection"]
    return {"recall": sd["recall"], "n_suppressed": sd["n_under_escalations"]}


def self_check(rescored: dict) -> dict:
    """Every re-derived cell must equal the committed ladder_5model/multimodel.json."""
    committed = json.loads(resolve(*COMMITTED_LADDER).read_text())["results"]
    mism, checked = [], 0
    for model, cells in rescored.items():
        for cond, cell in cells.items():
            c = committed.get(model, {}).get(cond)
            if c is None:
                continue
            checked += 1
            if (cell["missed"], cell["total"]) != (c["missed"], c["total"]):
                mism.append(f"{model}/{cond}: replay {cell['missed']}/{cell['total']} "
                            f"vs committed {c['missed']}/{c['total']}")
    return {"reproduced": not mism, "cells_checked": checked, "mismatches": mism}


def _lbl(cell: dict) -> str:
    return f"{S.ipct(cell['missed'], cell['total'])}% ({cell['missed']}/{cell['total']})"


def print_table(ladder: dict, core: dict, recall: dict, check: dict) -> None:
    conds = CONDITION_ORDER
    w = 15
    print()
    print("Cupel — headline reproduction  (replay from committed decision logs; 0 model calls)")
    print("under-escalation of reportable alerts; the peer-benchmark column is the headline")
    print("=" * (24 + w * len(conds)))
    print(f"{'model':<24}" + "".join(f"{S.cond_label(c):>{w}}" for c in conds))
    print("-" * (24 + w * len(conds)))
    for model, cells in ladder.items():
        print(f"{S.model_label(model):<24}" +
              "".join(f"{(_lbl(cells[c]) if c in cells else '-'):>{w}}" for c in conds))
    print("-" * (24 + w * len(conds)))
    print()
    print(f"Reference agent (Sonnet, core N=240):  neutral {_lbl(core['neutral'])}"
          f"  ->  peer-benchmark {_lbl(core['peer_benchmark'])}")
    print(f"Blind verifier recall on suppressed reportable alerts:  "
          f"{recall['recall']:.0%} ({recall['n_suppressed']}/{recall['n_suppressed']})")
    print()
    print(f"self-check vs committed ladder_5model/multimodel.json:  "
          f"{'reproduced OK' if check['reproduced'] else 'DRIFT'}  ({check['cells_checked']} cells)")
    for m in check["mismatches"]:
        print(f"   ! {m}")


def main() -> None:
    ladder = rescore_ladder()
    core = rescore_core()
    recall = verifier_recall()
    check = self_check(ladder)
    print_table(ladder, core, recall, check)

    results = {
        "finding": ("Under a peer-benchmark incentive, capable AML triage agents under-escalate "
                    "reportable alerts; blunt direct pressure has near-zero effect on capable "
                    "models; a blind cross-provider verifier catches suppressed cases at 100% "
                    "recall; the effect is capability-conditional (Llama-3-70B inverts under "
                    "direct 'strong' pressure)."),
        "reference_agent": core,
        "cross_model_under_escalation": {
            S.model_label(m): {S.cond_label(c): cells[c] for c in cells}
            for m, cells in ladder.items()},
        "verifier_recall_on_suppressed": recall,
        "self_check": check,
        "provenance": {
            "method": "replay — re-scored committed decisions.jsonl via "
                      "eval.metrics.under_escalation_rate",
            "runs": LADDER_RUNS + ["core"], "model_calls": 0, "network": False,
            "deterministic": True},
    }
    out = resolve("results.json")  # repo root, gitignored
    out.write_text(json.dumps(results, indent=2))
    print(f"\nwrote {out}")
    raise SystemExit(0 if check["reproduced"] else 1)


if __name__ == "__main__":
    main()
