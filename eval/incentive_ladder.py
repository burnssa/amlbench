"""Incentive-ladder chart — single model (Claude Sonnet 4.6).

Plots under-escalation across the five framings from the inducibility probe
(results/runs/probe/probe.json) for Claude Sonnet 4.6 only: the mundane
peer-benchmark framing induces suppression while the blunt 'harder' framings do
not. This 'shape beats strength' result is SONNET-SPECIFIC — the cross-model
ladder (eval.ladder_multimodel) shows it does not generalize (GPT-4o and Llama
bend to blunt pressure). All styling via eval/figstyle.py; no data altered.

    uv run python -m eval.incentive_ladder
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from eval import figstyle as S

ORDER = ["neutral", "throughput_backlog", "cost_efficiency", "strong", "quota"]


def plot(probe: dict, path: str) -> str:
    S.apply()
    conds = [c for c in ORDER if c in probe]
    x = np.arange(len(conds))
    w = 0.38
    fig, ax = plt.subplots(figsize=(11, 5.2))

    for i, c in enumerate(conds):
        cell = probe[c]
        col = S.cond_color(c)
        # all reportable (solid)
        ov = cell["under_escalation"]
        ax.bar(i - w / 2, ov, w, color=col, zorder=3)
        ax.text(i - w / 2, ov + 0.02, S.vlabel(cell["missed"], cell["escalate_truth"]),
                ha="center", va="bottom", fontsize=S.SIZE_VALUE)
        # subtle structuring target class (hatched, same condition color)
        ss = cell["per_typology"]["structuring_subtle"]
        ax.bar(i + w / 2, ss["rate"], w, facecolor=col, edgecolor="white", hatch="////", zorder=3)
        ax.text(i + w / 2, ss["rate"] + 0.02, S.vlabel(ss["missed"], ss["total"]),
                ha="center", va="bottom", fontsize=S.SIZE_VALUE)

    ax.set_xticks(x)
    ax.set_xticklabels([S.cond_label(c) for c in conds], fontsize=S.SIZE_TICK)
    S.style_underesc_axis(ax)

    # legend: solid vs hatched (metric), not color (color = condition)
    from matplotlib.patches import Patch
    ax.legend(handles=[
        Patch(facecolor=S.C_BLUNT, label="all reportable alerts (n=60)"),
        Patch(facecolor=S.C_BLUNT, hatch="////", edgecolor="white", label="subtle structuring — target class (n=16)"),
    ], loc="upper left", frameon=False, fontsize=S.SIZE_TICK)

    S.titles(
        fig,
        "Incentive shape beats strength — Claude Sonnet 4.6 (single model)",
        "Under-escalation by framing, seed 11, synthetic AMLSim battery. Sonnet-specific: blunt "
        "'harder' framings induce ~0%; only the mundane peer-benchmark bites. Does NOT generalize "
        "across models (see cross-model ladder).",
        y_title=0.985, y_sub=0.93,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def main() -> None:
    probe = json.load(open("results/runs/probe/probe.json"))
    out = plot(probe, "results/plots/incentive_ladder.png")
    print(f"[incentive_ladder] wrote {out}")


if __name__ == "__main__":
    main()
