"""Foreign-agent before/after chart — GPT-4o behind a vendor-style prompt.

Distinct harness from the in-house ladder: GPT-4o driven through the FULL pipeline
behind a vendor-style prompt (results/runs/ws2_foreign/). Under-escalation neutral
vs peer-benchmark, with the independent evaluator's catch. All styling via
eval/figstyle.py; no data altered.

    uv run python -m eval.ws2_foreign_chart
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from eval import figstyle as S


def plot(behavioral: dict, path: str) -> str:
    S.apply()
    ov = behavioral["overall"]
    conds = [("neutral", "neutral", S.C_NEUTRAL),
             ("peer-benchmark", "incentivized", S.C_PEER)]
    x = np.arange(len(conds))
    fig, ax = plt.subplots(figsize=(9, 5.6))

    for i, (lbl, key, col) in enumerate(conds):
        rate = ov[f"{key}_rate"]
        k, n = ov[f"{key}_missed"], ov[f"{key}_total"]
        ax.bar(i, rate, 0.5, color=col, zorder=3)
        ax.text(i, rate + 0.02, S.vlabel(k, n), ha="center", va="bottom", fontsize=S.SIZE_VALUE)

    ax.set_xticks(x)
    ax.set_xticklabels([c[0] for c in conds], fontsize=S.SIZE_TICK)
    S.style_underesc_axis(ax)

    S.titles(
        fig,
        "GPT-4o foreign-agent harness (vendor-style prompt) — neutral → peer-benchmark",
        "Cross-provider, full pipeline, seed 11, synthetic AMLSim battery. This is the FOREIGN-agent "
        "harness (60% peer-benchmark), distinct from GPT-4o's 48% in the in-house ladder.",
        y_title=0.985, y_sub=0.93,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def main() -> None:
    behavioral = json.load(open("results/runs/ws2_foreign/behavioral.json"))
    out = plot(behavioral, "results/plots/ws2_foreign.png")
    print(f"[ws2_foreign_chart] wrote {out}")


if __name__ == "__main__":
    main()
