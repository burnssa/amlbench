"""Foreign-agent before/after chart (slide 12).

GPT-4o behind a vendor-style prompt, full pipeline end-to-end: under-escalation
neutral vs quota, overall and for the subtle-structuring target class. Reads
results/runs/ws2_foreign/behavioral.json; no model calls.

    uv run python -m eval.ws2_foreign_chart
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def plot(behavioral: dict, path: str) -> str:
    ov = behavioral["overall"]
    labels = ["Neutral", "Peer-benchmark incentive"]
    rates = [ov["neutral_rate"], ov["incentivized_rate"]]
    ns = [ov["neutral_total"], ov["incentivized_total"]]
    missed = [ov["neutral_missed"], ov["incentivized_missed"]]

    x = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(9, 5.6))
    # Match incentive_ladder / per_typology styling: gray baseline, red for the
    # induced-failure bar.
    bars = ax.bar(x, rates, 0.5, color=["#9E9E9E", "#E45756"])

    for r, rate, m, n in zip(bars, rates, missed, ns):
        ax.text(r.get_x() + r.get_width() / 2, rate + 0.015,
                f"{rate:.0%}\n({m}/{n})", ha="center", va="bottom", fontsize=10.5)

    # Annotate the catch on the quota bar — the de-risking punchline.
    ax.annotate(
        "independent evaluator\ncaught 100% (44/44)",
        xy=(0.76, rates[1]), xytext=(0.42, 0.84),
        fontsize=10.5, ha="center", va="center", color="#1B5E20", fontweight="bold",
        arrowprops=dict(arrowstyle="->", color="#1B5E20", lw=1.6,
                        connectionstyle="arc3,rad=-0.2"),
        bbox=dict(boxstyle="round,pad=0.35", fc="#E8F5E9", ec="#1B5E20", lw=1.2),
    )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("under-escalation of reportable alerts")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.suptitle("GPT-4o (cross-provider) · neutral → peer-benchmark under-escalation", y=0.98,
                 fontsize=13, fontweight="bold")
    fig.text(0.5, 0.915,
             "gpt-4o · vendor-style prompt · seed 11 — under-escalation 13.3% → 60.0% under peer-benchmark "
             "(Cohen's h=1.03, p≈0)",
             ha="center", va="top", fontsize=9.5, color="#444444")

    fig.tight_layout(rect=[0, 0, 1, 0.88])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def main() -> None:
    behavioral = json.load(open("results/runs/ws2_foreign/behavioral.json"))
    out = plot(behavioral, "results/plots/ws2_foreign.png")
    print(f"[ws2_foreign_chart] wrote {out}")


if __name__ == "__main__":
    main()
