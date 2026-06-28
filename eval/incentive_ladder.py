"""Incentive-ladder chart: 'shape beats strength'.

Plots under-escalation across the five operating-context conditions from the
inducibility probe (results/runs/probe/probe.json) — showing that only the
mundane bureaucratic *quota* framing induced suppression, while blunter, ostensibly
'harder' pressure framings did not. Grouped bars: all reportable alerts vs the
subtle-structuring target class. Reads existing probe data; no model calls.

    uv run python -m eval.incentive_ladder
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Ladder order: control, the three blunt-pressure framings, then the quota framing.
ORDER = ["neutral", "throughput_backlog", "cost_efficiency", "strong", "quota"]
LABELS = {
    "neutral": "Neutral\n(control)",
    "throughput_backlog": "Throughput\nbacklog\n(blunt pressure)",
    "cost_efficiency": "Cost\nefficiency\n(blunt pressure)",
    "strong": "Strong\n(bonus + role\nreview)",
    "quota": "Peer benchmark\n(~5% peer rate\n+ quality-error penalty)",
}


def _pct(x: float) -> str:
    """Percent label with trailing zeros dropped: 0%, 3.3%, 31.7% (matches the subtitle)."""
    return f"{x * 100:.1f}".rstrip("0").rstrip(".") + "%"


def plot(probe: dict, path: str) -> str:
    conds = [c for c in ORDER if c in probe]
    overall = [probe[c]["under_escalation"] for c in conds]
    subtle = [probe[c]["per_typology"]["structuring_subtle"]["rate"] for c in conds]

    x = np.arange(len(conds))
    w = 0.38
    fig, ax = plt.subplots(figsize=(12, 5.8))
    b1 = ax.bar(x - w / 2, overall, w, label="all reportable alerts (n=60)", color="#B0B0B0")
    b2 = ax.bar(x + w / 2, subtle, w, label="subtle structuring — target class (n=16)", color="#E45756")

    # Highlight the one framing that worked.
    qi = conds.index("quota") if "quota" in conds else None
    if qi is not None:
        b1[qi].set_color("#6E6E6E")
        ax.annotate(
            "only this framing\ninduced suppression",
            xy=(qi, overall[qi]), xytext=(qi - 1.15, 0.52),
            fontsize=10, ha="center", color="#B3001B",
            arrowprops=dict(arrowstyle="->", color="#B3001B", lw=1.4),
        )

    for bars in (b1, b2):
        for r in bars:
            h = r.get_height()
            if h > 0.001:
                ax.text(r.get_x() + r.get_width() / 2, h + 0.012, _pct(h),
                        ha="center", va="bottom", fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels([LABELS.get(c, c) for c in conds], fontsize=9)
    ax.set_ylim(0, 0.7)
    ax.set_ylabel("under-escalation of reportable alerts")
    fig.suptitle("Incentive shape beats incentive strength", y=0.98, fontsize=13, fontweight="bold")
    fig.text(0.5, 0.915,
             "claude-sonnet-4-6 · seed 11 · same alerts — blunt 'harder' framings induced ~0%; "
             "a mundane peer-benchmark signal induced 31.7%",
             ha="center", va="top", fontsize=9.5, color="#444444")
    ax.legend(loc="upper left", frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))

    fig.tight_layout(rect=[0, 0, 1, 0.88])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def main() -> None:
    probe = json.load(open("results/runs/probe/probe.json"))
    out = plot(probe, "results/plots/incentive_ladder.png")
    print(f"[incentive_ladder] wrote {out}")


if __name__ == "__main__":
    main()
