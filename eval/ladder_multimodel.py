"""Cross-model incentive ladder — small multiples.

One mini-ladder per model (under-escalation across the five framings), so the
*shape* of susceptibility is comparable across models. Reads an existing ladder
run (default results/runs/ladder_5model/multimodel.json); no model calls.
All styling comes from eval/figstyle.py (formatting only — no data is altered).

    uv run python -m eval.ladder_multimodel
    uv run python -m eval.ladder_multimodel --run ladder_5model
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from common.config import load_config, resolve
from eval import figstyle as S

ORDER = ["neutral", "throughput_backlog", "cost_efficiency", "strong", "quota"]
# Canonical display order (capability-grouped within the Claude family, then others).
ROW_ORDER = ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
             "gpt-4o", "replicate/meta/meta-llama-3-70b-instruct"]


def plot(results: dict, path: str) -> str:
    S.apply()
    models = [m for m in ROW_ORDER if m in results] + [m for m in results if m not in ROW_ORDER]
    n = len(models)
    ncol = 2
    nrow = (n + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(11, 3.4 * nrow), squeeze=False)

    for idx, model in enumerate(models):
        ax = axes[idx // ncol][idx % ncol]
        cells = results[model]
        x = np.arange(len(ORDER))
        for j, c in enumerate(ORDER):
            cell = cells.get(c, {})
            v = cell.get("under_escalation", 0.0)
            k, tot = cell.get("missed"), cell.get("total")
            ax.bar(j, v, color=S.cond_color(c), zorder=3)
            if k is not None and tot:
                ax.text(j, v + 0.02, S.vlabel(k, tot), ha="center", va="bottom",
                        fontsize=S.SIZE_VALUE, color=S.C_TEXT)
        ax.set_xticks(x)
        ax.set_xticklabels([S.cond_label(c) for c in ORDER], fontsize=S.SIZE_TICK)
        S.style_underesc_axis(ax)
        ax.set_title(S.model_label(model), fontsize=11, fontweight="bold")

    for j in range(n, nrow * ncol):
        axes[j // ncol][j % ncol].axis("off")

    S.titles(
        fig,
        "Incentive ladder across models — peer-benchmark (red) vs blunt pressure (grey)",
        "Under-escalation of reportable alerts (n=60), seed 11, synthetic AMLSim battery. "
        "Peer-benchmark is the most potent framing in 4 of 5 models. "
        "Exception: Llama-3-70B clears 100% under blunt 'strong' (> its 52% peer-benchmark) — "
        "so 'shape > strength' is not universal.",
        y_title=0.995, y_sub=0.955,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.90])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="ladder_5model",
                    help="results/runs/<run>/multimodel.json to chart")
    args = ap.parse_args()
    cfg = load_config()
    data = json.loads(resolve("results", "runs", args.run, "multimodel.json").read_text())
    out = plot(data["results"], str(resolve(cfg["reporting"]["plots_dir"], "ladder_multimodel.png")))
    print(f"[ladder_multimodel] wrote {out}")


if __name__ == "__main__":
    main()
