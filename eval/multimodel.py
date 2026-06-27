"""WS1 — cross-model susceptibility (agent-only, behavioral arm).

Runs several agent models (cross-provider + open-weight) through the same
escalate-heavy battery under `neutral` and the inducing incentive, and reports
the under-escalation (suppression) rate per model — overall and for the
structuring target classes. The point: show the failure is a *category risk*
across providers, not a quirk of one model.

    uv run python -m eval.multimodel                 # uses config.generalization
    uv run python -m eval.multimodel --workers 6

Provider keys are read from .env (ANTHROPIC / OPENAI / REPLICATE). Models whose
key is missing are skipped with a clear note (so a partial run still works).
"""
from __future__ import annotations

import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from common.config import load_config, resolve
from common.io import read_jsonl, write_json, write_jsonl
from common.llm import MissingAPIKey, complete
from common.parallel import thread_map
from agent.triage import triage_one
from eval import metrics as M
from eval.probe import build_probe_set

ESCALATE = "SHOULD_ESCALATE"


def _cfg_for_model(model: str):
    c = load_config()
    c["agent"]["model"] = model
    return c


def _cell(model, alerts, condition, phrasing, workers):
    mcfg = _cfg_for_model(model)
    return thread_map(lambda a: triage_one(a, condition, phrasing, mcfg, mcfg["run"]["core_seed"]),
                      alerts, workers=workers, label=f"{model.split('/')[-1]}/{phrasing or 'neutral'}")


def _summary(decs, typologies):
    ue, miss, tot = M.under_escalation_rate(decs)
    per = {t: M.under_escalation_rate(decs, t)[0] for t in typologies}
    return {"under_escalation": round(ue, 4), "missed": miss, "total": tot,
            "over_escalation": round(M.false_escalation_rate(decs)[0], 4), "per_typology": per}


def _preflight(model) -> bool:
    """Cheap check that a model's provider key works; skip the model if not."""
    try:
        complete(model=model, system="ok", user="Reply with the word ok.", max_tokens=5, temperature=0.0)
        return True
    except MissingAPIKey as e:
        print(f"  [skip] {model}: {e}")
        return False
    except Exception as e:
        print(f"  [skip] {model}: preflight failed ({type(e).__name__}: {str(e)[:100]})")
        return False


def plot(results, incentive, path):
    models = list(results.keys())
    neu = [results[m]["neutral"]["under_escalation"] for m in models]
    inc = [results[m][incentive]["under_escalation"] for m in models]
    x = np.arange(len(models)); w = 0.38
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.bar(x - w / 2, neu, w, label="neutral", color="#4C78A8")
    ax.bar(x + w / 2, inc, w, label=f"incentivized ({incentive})", color="#E45756")
    ax.set_xticks(x); ax.set_xticklabels([m.split("/")[-1] for m in models], rotation=15, ha="right")
    ax.set_ylim(0, 1); ax.set_ylabel("under-escalation of reportable alerts")
    ax.set_title("Cross-model susceptibility to a quota incentive")
    ax.legend()
    fig.tight_layout(); fig.savefig(path, dpi=130); plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--only", default=None,
                    help="run only this model id and MERGE into existing multimodel.json")
    args = ap.parse_args()
    cfg = load_config()
    g = cfg["generalization"]
    seed = cfg["run"]["core_seed"]

    alerts = list(read_jsonl(resolve(cfg["dataset"]["output"])))
    probe = build_probe_set(alerts, g["clears"], seed)
    typologies = sorted({a["gt_typology"] for a in probe if a["ground_truth"]["label"] == ESCALATE})
    incentive = next((c for c in g["conditions"] if c != "neutral"), "quota")
    models = [args.only] if args.only else g["agent_models"]
    print(f"[multimodel] {len(probe)} alerts x {len(models)} model(s); neutral vs '{incentive}'"
          + (" (merge mode)" if args.only else ""))

    results, all_decs = {}, []
    for model in models:
        print(f"  [model] {model}")
        if not _preflight(model):
            continue
        cells = {}
        for cond in g["conditions"]:
            condition = "neutral" if cond == "neutral" else "incentivized"
            phrasing = None if cond == "neutral" else cond
            decs = _cell(model, probe, condition, phrasing, args.workers)
            decs = [d for d in decs if d]
            all_decs += decs
            cells[cond] = _summary(decs, typologies)
        results[model] = cells

    if not results:
        raise SystemExit("No models ran — check provider keys in .env.")

    out_dir = resolve("results", "runs", "multimodel")
    mm_path = out_dir / "multimodel.json"
    # Merge mode: preserve other models' results + decisions, replace this model's.
    if args.only and mm_path.exists():
        from common.io import read_json
        existing = read_json(mm_path)
        merged = existing.get("results", {})
        merged.update(results)
        results = merged
        typologies = sorted(set(typologies) | set(existing.get("typologies", [])))
        prior = [d for d in read_jsonl(out_dir / "decisions.jsonl") if d["agent_model"] != args.only]
        all_decs = prior + all_decs
    write_jsonl(out_dir / "decisions.jsonl", all_decs)
    write_json(mm_path, {"incentive": incentive, "results": results, "typologies": typologies})
    plot(results, incentive, resolve(cfg["reporting"]["plots_dir"], "multimodel.png"))

    # Console table.
    print("\n" + "=" * 88)
    print(f"{'model':<34}{'neutral':>10}{'  ' + incentive:>12}{'Δ':>10}{'struct_subtle Δ':>18}")
    print("-" * 88)
    for m, c in results.items():
        n, i = c["neutral"]["under_escalation"], c[incentive]["under_escalation"]
        ss_n = c["neutral"]["per_typology"].get("structuring_subtle", 0.0)
        ss_i = c[incentive]["per_typology"].get("structuring_subtle", 0.0)
        print(f"{m:<34}{n:>9.1%}{i:>12.1%}{('+' + format(i - n, '.0%')):>10}"
              f"{('+' + format(ss_i - ss_n, '.0%')):>18}")
    print("=" * 88)
    total = sum(d["usage"]["cost_usd"] for d in all_decs)
    print(f"agent calls: {len(all_decs)}  est. tracked spend: ${total:.2f} "
          f"(Replicate billed by time, not tracked)  -> {out_dir}/multimodel.json")


if __name__ == "__main__":
    main()
