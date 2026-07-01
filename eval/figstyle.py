"""Single source of truth for figure styling across all Cupel plots.

FORMATTING ONLY — this module never touches underlying data. Every plotting script
imports it so fonts, palette semantics, value-label format, y-axis range, gridlines,
title/subtitle placement, and DPI are identical everywhere.

Canonical model/condition names are derived from config/config.yaml (see MODEL_LABEL
/ COND_LABEL) — chart code must map raw run-config keys through these, never hand-type
display names.
"""
from __future__ import annotations

import math
import textwrap

import matplotlib as mpl
import matplotlib.pyplot as plt

# ── Fonts: one size per role, used everywhere ──────────────────────────────
FONT_FAMILY = "DejaVu Sans"
SIZE_TITLE = 14
SIZE_SUBTITLE = 9.5
SIZE_AXIS = 11
SIZE_TICK = 9.5
SIZE_VALUE = 9      # bar value labels
SIZE_ANNOT = 9      # annotations / callouts

# ── Palette with FIXED SEMANTICS (hex + meaning) ───────────────────────────
C_PEER = "#E45756"     # peer-benchmark (the incentivized headline condition) — accent/red
C_BLUNT = "#6E6E6E"    # blunt-pressure conditions (throughput / cost / strong) — mid grey
C_NEUTRAL = "#B0B0B0"  # neutral control — light grey
C_CAUGHT = "#2E7D32"   # verifier / "caught" callouts — green
C_TEXT = "#222222"
C_SUBTEXT = "#555555"
C_GRID = "#DDDDDD"

# Condition key (from config generalization.conditions) -> bar color.
CONDITION_COLOR = {
    "neutral": C_NEUTRAL,
    "throughput_backlog": C_BLUNT,
    "cost_efficiency": C_BLUNT,
    "strong": C_BLUNT,
    "quota": C_PEER,
}
# Condition key -> human-facing display label.
COND_LABEL = {
    "neutral": "neutral",
    "throughput_backlog": "throughput",
    "cost_efficiency": "cost",
    "strong": "strong",
    "quota": "peer-benchmark",
}
# Model id (from config generalization.agent_models) -> canonical display name.
MODEL_LABEL = {
    "claude-opus-4-8": "Claude Opus 4.8",
    "claude-sonnet-4-6": "Claude Sonnet 4.6",
    "claude-haiku-4-5-20251001": "Claude Haiku 4.5",
    "gpt-4o": "GPT-4o",
    "replicate/meta/meta-llama-3-70b-instruct": "Llama-3-70B-Instruct",
}

DPI = 130
YLIM_UNDERESC = (0, 1.06)  # 0–100% on every under-escalation chart (headroom for top labels)

# Shared standard subtitle tail — every figure states seed + synthetic provenance.
SYNTHETIC_NOTE = "Synthetic AMLSim-derived battery."


def model_label(key: str) -> str:
    return MODEL_LABEL.get(key, key.split("/")[-1])


def cond_label(key: str) -> str:
    return COND_LABEL.get(key, key)


def cond_color(key: str) -> str:
    return CONDITION_COLOR.get(key, C_BLUNT)


def ipct(k: int, n: int) -> int:
    """Integer percent of a raw fraction, round-half-up. DISPLAY ONLY — k/n is the datum."""
    return math.floor(100 * k / n + 0.5) if n else 0


def vlabel(k: int, n: int) -> str:
    """Standard bar value label: 'X% (k/n)' with integer percent."""
    return f"{ipct(k, n)}% ({k}/{n})"


def pct(r) -> str:
    """NaN-safe percent label for a rate in [0, 1]. Returns 'n/a' when the rate is
    undefined — None or NaN, e.g. a subset with zero samples in a small run — so a
    figure never crashes on `int(NaN)`. DISPLAY ONLY."""
    if r is None or r != r:  # r != r is True only for NaN
        return "n/a"
    return f"{ipct(round(r * 100), 100)}%"


def apply() -> None:
    """Apply global rcParams. Call once at the top of each plotting script."""
    mpl.rcParams.update({
        "font.family": FONT_FAMILY,
        "font.size": SIZE_TICK,
        "axes.titlesize": SIZE_TITLE,
        "axes.titleweight": "bold",
        "axes.labelsize": SIZE_AXIS,
        "axes.labelcolor": C_TEXT,
        "xtick.labelsize": SIZE_TICK,
        "ytick.labelsize": SIZE_TICK,
        "text.color": C_TEXT,
        "axes.edgecolor": "#999999",
        "axes.linewidth": 0.8,
        "figure.dpi": DPI,
        "savefig.dpi": DPI,
        "savefig.bbox": "tight",
    })


def style_underesc_axis(ax, ylabel: str = "under-escalation of reportable alerts") -> None:
    """0–100% y-axis, percent ticks, horizontal gridlines below bars, clean spines."""
    ax.set_ylim(*YLIM_UNDERESC)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_ylabel(ylabel)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.grid(axis="y", color=C_GRID, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def titles(fig, title: str, subtitle: str | None, y_title: float = 0.99, y_sub: float = 0.94,
           wrap: int | None = None) -> None:
    """Consistent title/subtitle placement and styling. The subtitle is auto-wrapped so it
    stays within the plot bounds (never a full-canvas single line). `wrap` overrides the
    auto width (characters); default ≈ figure width so lines fit inside the axes area."""
    fig.suptitle(title, fontsize=SIZE_TITLE, fontweight="bold", y=y_title, color=C_TEXT)
    if subtitle:
        if wrap is None:
            wrap = max(40, int(fig.get_figwidth() * 12))  # ~axes width at SIZE_SUBTITLE
        subtitle = textwrap.fill(" ".join(subtitle.split()), width=wrap)
        fig.text(0.5, y_sub, subtitle, ha="center", va="top",
                 fontsize=SIZE_SUBTITLE, color=C_SUBTEXT, linespacing=1.3)
