"""Per-typology under-escalation chart (under the quota incentive).

Shows that suppression concentrates in the judgment-call typologies while overt,
bright-line structuring stays at 0%. Reads results/runs/core/behavioral.json
(claude-sonnet-4-6, seed 11, quota); no model calls.

    uv run python -m eval.per_typology
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

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
    per = behavioral["per_typology"]
    typs = [t for t in ORDER if t in per]
    rates = [per[t]["incentivized_rate"] for t in typs]
    ns = [per[t]["incentivized_total"] for t in typs]
    missed = [per[t]["incentivized_missed"] for t in typs]

    x = np.arange(len(typs))
    fig, ax = plt.subplots(figsize=(11, 5.6))
    bars = ax.bar(x, rates, 0.62, color="#9E9E9E")

    for r, rate, m, n in zip(bars, rates, missed, ns):
        ax.text(r.get_x() + r.get_width() / 2, rate + 0.012,
                f"{rate:.0%}\n({m}/{n})", ha="center", va="bottom", fontsize=9.5)

    ax.set_xticks(x)
    ax.set_xticklabels([LABELS.get(t, t) for t in typs], fontsize=9.5)
    ax.set_ylim(0, 0.62)
    ax.set_ylabel("under-escalation of reportable alerts (under peer-benchmark incentive)")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.suptitle("The failure is typology-shaped — it hits the judgment calls",
                 y=0.98, fontsize=13, fontweight="bold")
    fig.text(0.5, 0.915,
             "claude-sonnet-4-6 · seed 11 · peer-benchmark incentive — bright-line overt structuring "
             "stays at 0%; suppression concentrates in the inference cases",
             ha="center", va="top", fontsize=9.5, color="#444444")

    fig.tight_layout(rect=[0, 0, 1, 0.88])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def main() -> None:
    behavioral = json.load(open("results/runs/core/behavioral.json"))
    out = plot(behavioral, "results/plots/per_typology.png")
    print(f"[per_typology] wrote {out}")


if __name__ == "__main__":
    main()
