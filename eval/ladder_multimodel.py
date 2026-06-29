"""Cross-model incentive ladder — small multiples.

One mini-ladder per model (under-escalation across the five framings), so the
*shape* of susceptibility is comparable across models. Reads an existing
multimodel ladder run (default results/runs/multimodel_ladder/multimodel.json);
no model calls.

    uv run python -m eval.ladder_multimodel
    uv run python -m eval.ladder_multimodel --run multimodel_ladder
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

ORDER = ["neutral", "throughput_backlog", "cost_efficiency", "strong", "quota"]
LABELS = ["neutral", "throughput", "cost", "strong", "peer-\nbench"]
BLUNT = {"throughput_backlog", "cost_efficiency", "strong"}


def _pct(x):
    return f"{x * 100:.0f}%"


def plot(results: dict, path: str) -> str:
    models = list(results.keys())
    n = len(models)
    ncol = 2
    nrow = (n + ncol - 1) // ncol
    fig, axes = plt.subplots(nrow, ncol, figsize=(11, 4.6 * nrow), squeeze=False)

    for idx, model in enumerate(models):
        ax = axes[idx // ncol][idx % ncol]
        cells = results[model]
        vals = [cells.get(c, {}).get("under_escalation", 0.0) for c in ORDER]
        colors = []
        for c in ORDER:
            if c == "neutral":
                colors.append("#9CA3AF")          # grey: baseline
            elif c == "quota":
                colors.append("#B3001B")          # red: the peer-benchmark headline
            else:
                colors.append("#6E6E6E")          # dark grey: blunt pressure
        x = np.arange(len(ORDER))
        bars = ax.bar(x, vals, color=colors)
        for r, v in zip(bars, vals):
            if v > 0.005:
                ax.text(r.get_x() + r.get_width() / 2, v + 0.02, _pct(v),
                        ha="center", va="bottom", fontsize=9)
        ax.set_xticks(x)
        ax.set_xticklabels(LABELS, fontsize=9)
        ax.set_ylim(0, 1.08)
        ax.set_title(model.split("/")[-1], fontsize=11, fontweight="bold")
        ax.set_ylabel("under-escalation")
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda t, _: f"{t:.0%}"))
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    # Hide any unused subplot.
    for j in range(n, nrow * ncol):
        axes[j // ncol][j % ncol].axis("off")

    fig.suptitle("Incentive ladder across models — peer-benchmark (red) vs blunt pressure (grey)",
                 y=0.99, fontsize=13, fontweight="bold")
    fig.text(0.5, 0.945,
             "Same 84-alert battery, seed 11. Peer-benchmark (red) is the most potent inducer in 4 of 5 "
             "models — including flagship Opus, which shrugs off blunt pressure (0%) yet still clears 37%. "
             "Only Llama suppresses more under blunt 'strong' pressure.",
             ha="center", va="top", fontsize=9, color="#444444")
    fig.tight_layout(rect=[0, 0, 1, 0.92])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="multimodel_ladder",
                    help="results/runs/<run>/multimodel.json to chart")
    args = ap.parse_args()
    cfg = load_config()
    data = json.loads(resolve("results", "runs", args.run, "multimodel.json").read_text())
    out = plot(data["results"], str(resolve(cfg["reporting"]["plots_dir"], "ladder_multimodel.png")))
    print(f"[ladder_multimodel] wrote {out}")


if __name__ == "__main__":
    main()
