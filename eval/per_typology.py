"""Per-typology under-escalation chart — single model (Claude Sonnet 4.6).

Under the peer-benchmark incentive, suppression concentrates in the judgment-call
typologies while overt, bright-line structuring stays at 0%. Reads
results/runs/core/behavioral.json (claude-sonnet-4-6, seed 11, N=240 core run,
peer-benchmark condition). All styling via eval/figstyle.py; no data altered.

    uv run python -m eval.per_typology
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from eval import figstyle as S

# Overt structuring first — it stays at 0%, the contrast that makes the point.
ORDER = ["structuring_overt", "structuring_subtle", "rapid_passthrough",
         "layering_gather", "fan_out_dispersion"]
LABELS = {
    "structuring_overt": "Structuring\novert\n(bright-line)",
    "structuring_subtle": "Structuring\nsubtle\n(realistic)",
    "rapid_passthrough": "Rapid\npass-through\n(layering)",
    "layering_gather": "Layering /\ngather-scatter",
    "fan_out_dispersion": "Fan-out\ndispersion",
}


def plot(behavioral: dict, path: str) -> str:
    S.apply()
    per = behavioral["per_typology"]
    typs = [t for t in ORDER if t in per]
    x = np.arange(len(typs))
    fig, ax = plt.subplots(figsize=(11, 5.6))

    for i, t in enumerate(typs):
        rate = per[t]["incentivized_rate"]
        k, n = per[t]["incentivized_missed"], per[t]["incentivized_total"]
        ax.bar(i, rate, 0.62, color=S.C_PEER, zorder=3)  # the peer-benchmark condition
        ax.text(i, rate + 0.02, S.vlabel(k, n), ha="center", va="bottom", fontsize=S.SIZE_VALUE)

    ax.set_xticks(x)
    ax.set_xticklabels([LABELS.get(t, t) for t in typs], fontsize=S.SIZE_TICK)
    S.style_underesc_axis(ax, "under-escalation of reportable alerts")

    S.titles(
        fig,
        "The failure is typology-shaped — Claude Sonnet 4.6, peer-benchmark incentive",
        "Per-typology under-escalation, seed 11, N=240 core run, synthetic AMLSim battery. "
        "Bright-line overt structuring stays at 0%; suppression concentrates in the inference cases.",
        y_title=0.985, y_sub=0.93,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.88])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def main() -> None:
    behavioral = json.load(open("results/runs/core/behavioral.json"))
    out = plot(behavioral, "results/plots/per_typology.png")
    print(f"[per_typology] wrote {out}")


if __name__ == "__main__":
    main()
