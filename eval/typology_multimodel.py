"""Cross-model per-typology heatmap — where suppression lands.

Under the peer-benchmark incentive, under-escalation per typology across all models
in the ladder run. Bright-line overt structuring stays at 0% in every model; the
judgment-call typologies bend. Reads results/runs/ladder_5model/multimodel.json.
Styling via eval/figstyle.py (cells are rates — the stored datum — labeled as
integer percent; per-typology k/n is not stored, so only percent is shown).

    uv run python -m eval.typology_multimodel
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np

from common.config import load_config, resolve
from eval import figstyle as S

TYP = [
    ("structuring_overt", "Structuring\novert\n(bright-line)"),
    ("structuring_subtle", "Structuring\nsubtle"),
    ("rapid_passthrough", "Rapid\npass-through"),
    ("layering_gather", "Layering /\ngather-scatter"),
    ("fan_out_dispersion", "Fan-out\ndispersion"),
]
ROW_ORDER = ["claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5-20251001",
             "gpt-4o", "replicate/meta/meta-llama-3-70b-instruct"]
# White -> peer-benchmark red (C_PEER): 0% reads clean, high under-escalation reads red.
CMAP = LinearSegmentedColormap.from_list("wr", ["#FFFFFF", S.C_PEER])


def plot(results: dict, path: str, cond: str = "quota") -> str:
    S.apply()
    models = [m for m in ROW_ORDER if m in results] + [m for m in results if m not in ROW_ORDER]
    typs = [(k, lbl) for k, lbl in TYP
            if any(k in c.get(cond, {}).get("per_typology", {}) for c in results.values())]
    M = np.array([[results[m].get(cond, {}).get("per_typology", {}).get(k, np.nan)
                   for k, _ in typs] for m in models], dtype=float)

    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    im = ax.imshow(M, cmap=CMAP, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(typs))); ax.set_xticklabels([lbl for _, lbl in typs], fontsize=S.SIZE_TICK)
    ax.set_yticks(range(len(models))); ax.set_yticklabels([S.model_label(m) for m in models], fontsize=S.SIZE_TICK)
    for i in range(len(models)):
        for j in range(len(typs)):
            v = M[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{math.floor(v * 100 + 0.5):d}%",   # round-half-up, matches figstyle.ipct
                        ha="center", va="center", fontsize=S.SIZE_VALUE,
                        color="white" if v > 0.55 else S.C_TEXT,
                        fontweight="bold" if v >= 0.5 else "normal")
    S.titles(
        fig,
        "Where suppression lands — per-typology under-escalation under the peer benchmark",
        "5 models, seed 11, synthetic AMLSim battery. Bright-line overt structuring stays at 0% in "
        "every model; the judgment-call typologies bend. (GPT-4o and Llama also miss subtle "
        "structuring at neutral baseline — partly capability, not incentive.)",
        y_title=0.99, y_sub=0.925,
    )
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
    cbar.set_label("under-escalation of reportable alerts", fontsize=S.SIZE_AXIS)
    cbar.ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda t, _: f"{t:.0%}"))
    fig.tight_layout(rect=[0, 0, 1, 0.86])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="ladder_5model")
    args = ap.parse_args()
    cfg = load_config()
    data = json.loads(resolve("results", "runs", args.run, "multimodel.json").read_text())
    out = plot(data["results"], str(resolve(cfg["reporting"]["plots_dir"], "typology_multimodel.png")))
    print(f"[typology_multimodel] wrote {out}")


if __name__ == "__main__":
    main()
