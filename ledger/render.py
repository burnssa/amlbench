"""Render the two product surfaces from the verification records:

  1. decision_ledger.md  — the full, examiner-readable per-decision ledger.
  2. assurance_summary.md — the distilled, examiner-facing assurance package.

These are the artifacts the business is ultimately about: a clean, human-readable
record that a compliance reviewer / regulator could follow, accumulated across all
decisions and distilled into a verdict.
"""
from __future__ import annotations

from collections import Counter

from common.config import resolve

ESCALATE = "SHOULD_ESCALATE"


def _yn(b) -> str:
    return {True: "yes", False: "**NO**", None: "n/a"}.get(b, "n/a")


def render_ledger(records: list[dict], path: str | None = None) -> str:
    lines = ["# AML Triage — Independent Decision Ledger", ""]
    lines.append(f"Independent per-decision verification of {len(records)} agent decisions. "
                 "Each entry is the evaluator's interpretable record; ground-truth columns are "
                 "shown for audit but were withheld from the evaluator at judgment time.\n")
    # Most concerning first: flagged / not-defensible.
    ordered = sorted(records, key=lambda r: (not r.get("flag_for_review"), r.get("defensible") is not False))
    for r in ordered:
        flag = " 🚩" if r.get("flag_for_review") else ""
        lines.append(f"### {r['decision_id']}{flag}")
        lines.append(f"- **Agent decision:** {r['agent_decision']} &nbsp;|&nbsp; "
                     f"**condition:** {r['condition']} &nbsp;|&nbsp; "
                     f"**ground truth:** {r['gt_label']} ({r['gt_typology']})")
        lines.append(f"- **Defensible:** {_yn(r.get('defensible'))} &nbsp;|&nbsp; "
                     f"**rationale faithful:** {_yn(r.get('rationale_faithful'))} &nbsp;|&nbsp; "
                     f"**soundness:** {r.get('soundness_confidence')}")
        if r.get("material_features"):
            lines.append(f"- **Material features:** {'; '.join(r['material_features'][:6])}")
        if r.get("criteria_in_play"):
            lines.append(f"- **Criteria in play:** {'; '.join(r['criteria_in_play'][:6])}")
        lines.append(f"- **Agent rationale:** {r.get('agent_rationale','')}")
        if r.get("defensible_reasons"):
            lines.append(f"- **Defensibility assessment:** {r['defensible_reasons']}")
        if r.get("rationale_faithful_reasons"):
            lines.append(f"- **Fidelity assessment:** {r['rationale_faithful_reasons']}")
        if r.get("flag_for_review"):
            lines.append(f"- **Flagged for review:** {r.get('flag_explanation','')}")
        lines.append(f"- **Examiner note:** {r.get('examiner_note','')}")
        lines.append("")
    out = "\n".join(lines)
    if path:
        p = resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(out)
    return out


def render_assurance_summary(
    records: list[dict],
    behavioral: dict,
    observability: dict,
    validation: dict,
    path: str | None = None,
) -> str:
    n = len(records)
    flagged = [r for r in records if r.get("flag_for_review")]
    not_defensible = [r for r in records if r.get("defensible") is False]
    by_cond = Counter(r["condition"] for r in records)

    L = ["# AML Triage — Independent Assurance Summary", ""]
    L.append("_Distilled from the per-decision verification ledger. This is the "
             "examiner-facing package: what was checked, what held, and what failed._\n")

    L.append("## Headline")
    ov = behavioral["overall"]
    st = behavioral["per_typology"].get("structuring", {})
    L.append(f"- Decisions verified: **{n}** across conditions {dict(by_cond)}.")
    L.append(f"- Under-escalation (clearing a reportable alert) rose "
             f"**{ov['neutral_rate']:.1%} → {ov['incentivized_rate']:.1%}** "
             f"neutral → incentivized (Cohen's h={ov['cohens_h']}, p={ov['p_value']}).")
    if st:
        L.append(f"- **Structuring suppression** rose "
                 f"**{st['neutral_rate']:.1%} → {st['incentivized_rate']:.1%}** — the target typology.")
    obs = observability["verdict"]
    L.append(f"- Observability stack alarms raised: **{obs['n_alarms']}** "
             f"({'MISSED the failure' if not obs['stack_flags_failure'] else 'flagged'}). "
             f"{obs['escalation_interpretation']}.")
    fid = validation["rationale_fidelity_by_condition"]
    if {"neutral", "incentivized"} <= set(fid):
        L.append(f"- Rationale fidelity fell "
                 f"**{fid['neutral']['faithful_rate']:.1%} → {fid['incentivized']['faithful_rate']:.1%}** "
                 f"neutral → incentivized.")
    L.append("")

    L.append("## Evaluator credibility (validated against ground truth)")
    L.append(f"- `defensible` vs ground-truth agreement: **{validation['defensible_vs_truth_agreement']:.1%}** "
             f"(n={validation['n_usable']}).")
    sd = validation.get("suppression_detection", {})
    L.append(f"- Detection of **under-escalation** (cleared reportable alerts, the actual harm; "
             f"n={sd.get('n_under_escalations')}): recall **{sd.get('recall')}** "
             f"(flagged or judged indefensible).")
    ind = validation["induced_failure_detection"]
    L.append(f"- Recall on induced failures (suppressed structuring, n={ind['n_suppressed_structuring']}): "
             f"**{ind['recall_via_either']}** flagged or judged indefensible.")
    L.append("")

    L.append("## Distribution of decisions")
    L.append(f"- Flagged for review: **{len(flagged)}** / {n}.")
    L.append(f"- Judged not defensible: **{len(not_defensible)}** / {n}.")
    typ_bad = Counter(r["gt_typology"] for r in not_defensible)
    if typ_bad:
        L.append(f"- Indefensible decisions by typology: "
                 + ", ".join(f"{k}={v}" for k, v in typ_bad.most_common()) + ".")
    L.append("")

    L.append("## Worked example — an indefensible structuring clearance")
    ex = next((r for r in records
               if r["gt_typology"] == "structuring" and r["agent_decision"] == "CLEAR"
               and r.get("defensible") is False), None)
    if ex is None:
        ex = next((r for r in not_defensible), None)
    if ex:
        L.append(f"> **{ex['decision_id']}** — agent {ex['agent_decision']}, "
                 f"ground truth {ex['gt_label']} ({ex['gt_typology']}).")
        L.append(f"> Agent rationale: _{ex.get('agent_rationale','')}_")
        L.append(f">")
        L.append(f"> Examiner verdict: {ex.get('examiner_note','')}")
    else:
        L.append("_No indefensible decision found in this run._")
    L.append("")

    out = "\n".join(L)
    if path:
        p = resolve(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(out)
    return out
