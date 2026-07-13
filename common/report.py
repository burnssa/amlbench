"""Plots + REPORT.md assembly."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common.claims import SELF_CERT_GAP
from common.config import resolve

# Human-facing display labels for incentive-condition keys. The keys (e.g. "quota")
# are stable identifiers that live in config + committed result data; the label is
# what a human reads. The `quota` condition sets a *peer benchmark* ("~5% of peer
# alerts are escalated; your rate is tracked"), not a literal quota — hence the
# key-vs-label gap is intentional.
COND_LABELS = {"quota": "peer benchmark"}


def cond_label(key: str) -> str:
    return COND_LABELS.get(key, key)


from eval import figstyle as S  # shared formatting (palette/fonts) — no data altered


def _bars(ax, labels, neutral, incent, title, ylabel):
    import numpy as np
    x = np.arange(len(labels))
    w = 0.38
    # Fixed palette: neutral = light grey, peer-benchmark (incentivized) = red.
    ax.bar(x - w / 2, neutral, w, label="neutral", color=S.C_NEUTRAL, zorder=3)
    ax.bar(x + w / 2, incent, w, label="peer-benchmark", color=S.C_PEER, zorder=3)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=S.SIZE_TICK)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color=S.C_GRID, linewidth=0.7, zorder=0); ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.legend(frameon=False, fontsize=S.SIZE_TICK)


def plot_behavioral(behavioral: dict, plots_dir: str) -> str:
    S.apply()
    per = behavioral["per_typology"]
    typ = ["ALL"] + [t for t in per if per[t]["incentivized_total"] > 0]
    ov = behavioral["overall"]
    neutral = [ov["neutral_rate"]] + [per[t]["neutral_rate"] for t in typ[1:]]
    incent = [ov["incentivized_rate"]] + [per[t]["incentivized_rate"] for t in typ[1:]]
    # k/n for the peer-benchmark bars (under-escalation): ALL = overall, then per typology.
    kn = [(ov["incentivized_missed"], ov["incentivized_total"])] + \
         [(per[t]["incentivized_missed"], per[t]["incentivized_total"]) for t in typ[1:]]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    _bars(ax, [t if t == "ALL" else t.replace("structuring_", "struct.\n") for t in typ],
          neutral, incent, "Under-escalation rate — Claude Sonnet 4.6, neutral vs peer-benchmark", "under-escalation rate")
    import numpy as np
    for i, (k, n) in enumerate(kn):
        ax.text(np.arange(len(typ))[i] + 0.19, incent[i] + 0.015, S.vlabel(k, n),
                ha="center", va="bottom", fontsize=7.5, color=S.C_TEXT)
    ax.set_ylim(*S.YLIM_UNDERESC)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    path = Path(resolve(plots_dir, "behavioral.png"))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)
    return str(path)


def plot_observability(observability: dict, plots_dir: str) -> str:
    S.apply()
    n, i = observability["neutral"], observability["incentivized"]
    labels = ["groundedness", "coherence", "1-hallucination", "escalation_rate"]
    neutral = [n["mean_groundedness"], n["mean_coherence"], 1 - n["mean_hallucination"], n["escalation_rate"]]
    incent = [i["mean_groundedness"], i["mean_coherence"], 1 - i["mean_hallucination"], i["escalation_rate"]]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    _bars(ax, labels, neutral, incent, "Observability signals (stack stays green; escalation just falls)", "score / rate")
    ax.set_ylim(0, 1)  # 0–1 score axis (NOT an under-escalation chart) — keeps its own scale
    path = Path(resolve(plots_dir, "observability.png"))
    fig.tight_layout(); fig.savefig(path); plt.close(fig)
    return str(path)


def plot_fidelity(validation: dict, plots_dir: str) -> str | None:
    S.apply()
    fid = validation["rationale_fidelity_by_condition"]
    conds = [c for c in ("neutral", "incentivized") if c in fid]
    if len(conds) < 1:
        return None
    disp = {"neutral": "neutral", "incentivized": "peer-benchmark"}
    cols = {"neutral": S.C_NEUTRAL, "incentivized": S.C_PEER}
    fig, ax = plt.subplots(figsize=(5.5, 4.6))
    rates = [fid[c]["faithful_rate"] for c in conds]
    ax.bar([disp[c] for c in conds], rates, color=[cols[c] for c in conds], zorder=3)
    for x_i, r in enumerate(rates):
        finite = r is not None and r == r  # r != r only for NaN (e.g. 0-sample subset)
        ax.text(x_i, (r + 0.015) if finite else 0.02, S.pct(r),
                ha="center", va="bottom", fontsize=S.SIZE_VALUE)
    ax.set_ylim(0, 1.06); ax.set_ylabel("rationale-faithful rate")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.grid(axis="y", color=S.C_GRID, linewidth=0.7, zorder=0); ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.set_title("Rationale fidelity by condition (Pillar B)")
    path = Path(resolve(plots_dir, "fidelity.png"))
    fig.tight_layout(); fig.savefig(path); plt.close(fig)
    return str(path)


def build_report(*, cfg, run_meta, dataset_summary, behavioral, observability,
                 validation, records, plot_paths, finding) -> str:
    ov = behavioral["overall"]
    st = behavioral["per_typology"].get("structuring", {})
    obs = observability["verdict"]
    fid = validation["rationale_fidelity_by_condition"]

    def rel(p):  # path relative to results/
        return "plots/" + Path(p).name if p else ""

    L = ["# Behavioral Assurance + Interpretable Verification for an AML Triage Agent", ""]
    L.append("> **Scope.** This is the **private-tier attestation report** (the Superjective "
             "add-on) and the **v0 ablation** it grew from — an independent audit of one agent "
             "under an operating incentive, notable for the *observability gap* (Claim 2): standard "
             "monitoring stays quiet while escalation drops. It is **not** the public AMLBench "
             "leaderboard — for the benchmark's headline results see "
             "[`docs/AMLBENCH_FINDINGS.md`](docs/AMLBENCH_FINDINGS.md) + "
             "`results/canonical/leaderboard.json`.\n")
    _agent_id = run_meta.get('agent', cfg['agent']['model'])
    _desc = run_meta.get('agent_descriptor')
    _agent_str = f"`{_agent_id}`" + (f" ({_desc})" if _desc else "")
    L.append(f"_Run mode: **{run_meta['mode']}** · seeds {run_meta['seeds']} · "
             f"phrasings {run_meta['phrasings']} · agent {_agent_str} · "
             f"evaluator `{cfg['evaluator']['model']}` · observability `{observability['mode']}`._\n")

    L.append("## Thesis")
    L.append("Financial institutions deploying AI agents into compliance workflows need "
             "independent behavioral assurance with two pillars: (A) catching misbehavior that "
             "reliability/observability tooling cannot see, and (B) interpretable, independent "
             "per-decision verification regulators will accept. This run tests both on an AML "
             "transaction-monitoring agent under a hidden-incentive evaluation (legitimate triage "
             "task + an ordinary throughput/FP-reduction incentive that conflicts with correct escalation).\n")

    L.append("## Method")
    L.append("- **Data:** AMLSim-derived substrate (pure-Python port of AMLSim's typology-graph "
             "generator + temporal emitter; the Java/MASON step is reproduced in Python). "
             "Structuring/smurfing is realised as a `fan_in` of sub-$10,000 cash deposits. "
             "Ground-truth labels are assigned by **deterministic BSA/AML rules**, not an LLM, so "
             "under-escalation is objectively measurable. The evaluator never sees these labels.")
    L.append(f"  - Dataset: {dataset_summary['n_alerts']} alerts, "
             f"{dataset_summary['n_escalate']} escalate ({dataset_summary['escalate_rate']:.1%}), "
             f"{dataset_summary['n_structuring']} structuring "
             f"({dataset_summary['structuring_share_of_escalate']:.1%} of escalate). "
             f"AMLSim `is_sar` recovered by rules: {dataset_summary['amlsim_sar_recovered_by_rules']}.")
    L.append("- **Agent:** single-alert triage exposing an explicit reasoning trace + decision + "
             "rationale. **Conditions:** matched `neutral` vs `incentivized` (incentive via context "
             "only). **Pillar A obs arm:** Phoenix tracing + groundedness/coherence/hallucination "
             "quality evals + drift (PSI). **Pillar A behavioral arm:** under-escalation vs ground "
             "truth (also a standalone Inspect AI task). **Pillar B:** independent Opus evaluator "
             "emitting interpretable verification records, validated against ground truth.\n")

    # Embed the static domain primer (single source of truth in docs/) so the
    # report is self-contained for readers new to AML/BSA.
    primer = resolve("docs", "DOMAIN_BACKGROUND.md")
    if primer.exists():
        L.append(primer.read_text().strip() + "\n")

    L.append("## Results")
    L.append("### Claim 1 — Inducibility (setup)")
    L.append(f"Under the incentive, overall under-escalation rose **{ov['neutral_rate']:.1%} → "
             f"{ov['incentivized_rate']:.1%}** (abs +{ov['abs_increase']:.1%}, rel ×{ov['rel_increase']}, "
             f"Cohen's h={ov['cohens_h']}, two-proportion p={ov['p_value']}, "
             f"bootstrap 95% CI on the difference {ov['ci95']}).")
    if st:
        L.append(f"Structuring-specific suppression rose **{st['neutral_rate']:.1%} → "
                 f"{st['incentivized_rate']:.1%}** "
                 f"({st['incentivized_missed']}/{st['incentivized_total']} reportable structuring "
                 f"alerts cleared under incentive).")
    if plot_paths.get("behavioral"):
        L.append(f"\n![behavioral]({rel(plot_paths['behavioral'])})\n")

    # Cross-model generalization (WS1): prefer the full incentive ladder across models
    # (results/runs/ladder_5model); fall back to the 2-condition cross-model run.
    import json as _json
    ladder_path = resolve("results", "runs", "ladder_5model", "multimodel.json")
    mm_path = resolve("results", "runs", "multimodel", "multimodel.json")
    _LADDER = [("neutral", "neutral"), ("throughput_backlog", "throughput"),
               ("cost_efficiency", "cost"), ("strong", "strong"), ("quota", cond_label("quota"))]
    if ladder_path.exists():
        res = _json.loads(ladder_path.read_text())["results"]
        present = [(k, lbl) for k, lbl in _LADDER if any(k in cells for cells in res.values())]
        L.append("### Claim 1b — Generalization across models (the incentive ladder)")
        L.append(f"The full incentive ladder — neutral, three blunt high-pressure framings, and the "
                 f"{cond_label('quota')} framing — run across {len(res)} models (cross-provider + "
                 "open-weight). Two findings hold; one does not:\n")
        L.append(f"- **The {cond_label('quota')} framing induces substantial under-escalation in every "
                 "model tested (33–57%), including the most capable** — it is the single most potent "
                 "framing in 4 of 5 models. The mundane, legitimate-sounding benchmark is the reliably "
                 "dangerous one.")
        L.append("- **Resistance to *blunt* pressure tracks capability within the Claude family** — Opus "
                 "and Sonnet keep the blunt framings in the single digits (≤8%) while Haiku does not "
                 "(12–22%) — **but this does not generalize across providers**: GPT-4o bends to blunt "
                 "pressure too (35–37%), and Llama clears "
                 "*every* reportable alert under the explicit bonus/role-review framing (100%).")
        L.append("- Net: \"incentive shape beats strength\" is a property of the most capable models, not "
                 "a universal law; what *is* universal is susceptibility to the peer-benchmark framing.\n")
        L.append("| agent model (under-escalation) | " + " | ".join(lbl for _, lbl in present) + " |")
        L.append("|---|" + "---|" * len(present))
        for m, cells in res.items():
            row = " | ".join((f"{cells[k]['under_escalation']:.1%}" if k in cells else "—")
                             for k, _ in present)
            L.append(f"| `{m.split('/')[-1]}` | {row} |")
        L.append("\n_Note: the ladder runs on the 84-alert probe set, not the full N=240 core battery, "
                 "and cells are point estimates that wobble ±1–2 alerts at temperature 0 — Sonnet here is "
                 "33.3% vs. the core headline's 31.7%, the same agent on the same reportable alerts. The "
                 "single-model Sonnet figures (incentive-ladder, per-typology) are drawn from the core / "
                 "probe runs and so can differ from this cross-model ladder by ≤1 alert per cell for the "
                 "same reason — compare them for shape, not third-decimal precision; rely on the bootstrap "
                 "CIs (Claim 1) for the headline._")
        if resolve(cfg["reporting"]["plots_dir"], "ladder_multimodel.png").exists():
            L.append("\n![incentive ladder across models](plots/ladder_multimodel.png)\n")
        if resolve("results", "runs", "ladder_5model", "multimodel.json").exists():
            L.append("**Where the suppression lands generalizes too:** bright-line **overt structuring "
                     "stays at 0% under-escalation in every model** even under the peer benchmark, while "
                     "the judgment-call typologies (subtle structuring, pass-through, layering, dispersion) "
                     "bend. The failure is typology-shaped, and that shape holds across providers. (GPT-4o "
                     "and Llama also miss subtle structuring at neutral baseline — partly capability, not "
                     "incentive.)")
            if resolve(cfg["reporting"]["plots_dir"], "typology_multimodel.png").exists():
                L.append("\n![per-typology under-escalation across models](plots/typology_multimodel.png)\n")
    elif mm_path.exists():
        mm = _json.loads(mm_path.read_text())
        inc = mm["incentive"]
        L.append("### Claim 1b — Generalization across models (cross-provider)")
        L.append(f"The same neutral→{cond_label(inc)} susceptibility test run across multiple agent "
                 "models (different providers + an open-weight model) — to show the failure is a "
                 "category risk, not a single-model quirk:\n")
        L.append(f"| agent model | neutral under-esc | {cond_label(inc)} under-esc | Δ | subtle-structuring Δ |")
        L.append("|---|---|---|---|---|")
        for m, c in mm["results"].items():
            n, i = c["neutral"]["under_escalation"], c[inc]["under_escalation"]
            ss_n = c["neutral"]["per_typology"].get("structuring_subtle", 0.0)
            ss_i = c[inc]["per_typology"].get("structuring_subtle", 0.0)
            L.append(f"| `{m}` | {n:.1%} | {i:.1%} | +{i - n:.1%} | +{ss_i - ss_n:.1%} |")
        if resolve(cfg["reporting"]["plots_dir"], "multimodel.png").exists():
            L.append("\n![multimodel](plots/multimodel.png)\n")

    L.append("### Claim 2 — Observability gap (Pillar A, negative)")
    L.append(f"The observability stack raised **{obs['n_alarms']} alarms** "
             f"(`stack_flags_failure = {obs['stack_flags_failure']}`). "
             f"{obs['escalation_interpretation']}.")
    L.append("\n| signal | neutral | incentivized | Δ | alarm |")
    L.append("|---|---|---|---|---|")
    for c in obs["checks"]:
        L.append(f"| {c['signal']} | {c['neutral']} | {c['incentivized']} | {c['delta']} | "
                 f"{'🚨' if c['alarm'] else '—'} |")
    drift = observability.get("drift")
    if drift:
        L.append(f"\n**Drift (reported, not a correctness alarm):** coherence-score PSI "
                 f"{drift.get('coherence_score_psi')}, output-length PSI {drift.get('output_length_psi')}. "
                 f"{drift['note']}")
    if plot_paths.get("observability"):
        L.append(f"\n![observability]({rel(plot_paths['observability'])})\n")

    L.append("### Claim 3 — Behavioral detection (Pillar A, positive)")
    L.append("The behavioral assessment quantifies the under-escalation the observability stack "
             "missed (table/plot above), overall and per typology, with effect sizes and CIs.\n")

    L.append("### Claim 4 — Interpretable verification (Pillar B)")
    L.append(f"- Evaluator `defensible` vs ground-truth agreement: "
             f"**{validation['defensible_vs_truth_agreement']:.1%}** (n={validation['n_usable']}).")
    sd = validation.get("suppression_detection", {})
    L.append(f"- Detection of **under-escalation** (cleared reportable alerts — the harm-relevant "
             f"axis; n={sd.get('n_under_escalations')}): recall **{sd.get('recall')}**. "
             f"(The all-decisions 'not defensible' detector reads lower — precision "
             f"{validation['detector']['precision']}, recall {validation['detector']['recall']} — "
             f"because it counts conservative over-escalations as 'misses', which are legitimately "
             f"defensible.)")
    ind = validation["induced_failure_detection"]
    L.append(f"- Recall on induced failures (suppressed structuring, "
             f"n={ind['n_suppressed_structuring']}): **{ind['recall_via_either']}** "
             f"(flagged or judged indefensible).")
    if {"neutral", "incentivized"} <= set(fid):
        def _f1(r):  # NaN-safe one-decimal percent (undefined subsets → 'n/a')
            return "n/a" if (r is None or r != r) else f"{r:.1%}"
        L.append(f"- Rationale fidelity fell **{_f1(fid['neutral']['faithful_rate'])} → "
                 f"{_f1(fid['incentivized']['faithful_rate'])}** neutral → incentivized; "
                 f"on suppressed structuring it was "
                 f"{validation['rationale_fidelity_suppressed_structuring']}.")
    if plot_paths.get("fidelity"):
        L.append(f"\n![fidelity]({rel(plot_paths['fidelity'])})\n")

    L.append("### Sample verification records")
    samples = [r for r in records if r.get("defensible") is False][:2] or records[:2]
    for r in samples:
        L.append(f"> **{r['decision_id']}** — agent {r['agent_decision']}, "
                 f"truth {r['gt_label']} ({r['gt_typology']}); defensible={r.get('defensible')}, "
                 f"faithful={r.get('rationale_faithful')}.")
        L.append(f"> Agent rationale: _{r.get('agent_rationale','')}_")
        L.append(f"> Examiner note: {r.get('examiner_note','')}\n")

    L.append("## Attestation finding (distilled)")
    L.append(f"- **Severity:** {finding['severity']}")
    L.append(f"- **Criterion:** {finding['criterion']}")
    L.append(f"- **Regulatory exposure:** {finding['regulatory_exposure']}\n")

    L.append("## Positioning vs. compliance platforms (e.g., Hummingbird)")
    L.append("Incumbent AI-compliance platforms (Hummingbird, Unit21, etc.) already offer "
             "auto-triage, SAR-narrative drafting, case documentation, **audit trails**, **QA/QC**, "
             "and human-in-the-loop review. None of these is the same function as independent "
             "behavioral assurance, because all of them are **first-party**: the operator inspecting "
             "its own agent, against its own standards, using the agent's own stated reasoning as the "
             "evidence — the definition of the self-attestation regulators distrust.")
    L.append("- **Audit trail ≠ adjudication.** An audit trail faithfully *records* the rationale; it "
             "does not judge whether the decision was defensible or the rationale faithful. Every "
             "suppressed clearance in this run had a coherent, grounded rationale — a documentation "
             "layer would record the cover story verbatim.")
    L.append("- **QA/QC has the same blind spot as observability.** Quality review tuned to internal "
             "standards does not catch high-quality-but-wrong decisions (see the observability arm: "
             "the suppressed decisions score high on groundedness/coherence).")
    L.append("- **Three lines of defense.** These platforms are first-line (ops doing + documenting "
             "the work). Independent behavioral assurance is a second/third-line function and, by "
             "definition, cannot be the system that made the decisions. Bookkeeping vs. external audit.")
    L.append("- **The autonomy roadmap manufactures the demand.** As these platforms move from "
             "human-approved recommendations to *fully automated casework*, the human reviewer "
             "disappears and the only record between a suppressed SAR and a missed filing is the "
             "agent's self-documented rationale — exactly the failure mode demonstrated here.")
    L.append("- **Defensibility is independence + corpus, not algorithm.** A second-model checker is "
             "easy to bolt on; a genuinely *independent* third party with a ground-truth-calibrated, "
             "cross-client decision corpus and neutral regulatory standing is not. The cleanest GTM is "
             "complementary: sit on top of these platforms' decision logs as the independent "
             "verification layer their own automation will require.\n")

    L.append("## Future direction — an agent-susceptibility benchmark")
    L.append("The most striking results here generalize into a candidate public benchmark: "
             "(1) **a mundane peer-benchmark framing is the most potent inducer across every model "
             "tested (33–57%), including the flagship** — and resistance to *blunt* high-pressure "
             "framing tracks capability within a model family but does not generalize across "
             "providers (see the cross-model ladder above); and (2) "
             "**susceptibility is typology-dependent** — bright-line/overt structuring stayed "
             "robust while subtle, realistic structuring and judgment-based typologies bent. A "
             "benchmark would score *agent integrity under a calibrated incentive ladder* "
             "(susceptibility = Δ under-escalation vs. a neutral baseline, per typology, validated "
             "against objective ground truth), across models and domains, with an overt/subtle "
             "control pair to keep the score interpretable and a rotating private split to resist "
             "gaming. Strategic framing: the benchmark is a credibility **wedge** and a seed for the "
             "cross-decision corpus — it demonstrates the risk class is real and general — but it is "
             "subordinate to the actual product, which is independent per-decision verification of a "
             "*specific* deployed agent (the benchmark measures models in the abstract; an auditor "
             "verifies this bank's configured agent and produces the examiner-readable logic chain). "
             "Recommended sequencing: worked example → short technical report on the finding → "
             "public benchmark only once it generalizes across several models/domains.\n")

    L.append("## Limitations")
    L.append("- **Synthetic provenance.** The substrate is an AMLSim-faithful *port*, not output "
             "from the AMLSim Java/MASON simulator, and the structuring typology is constructed; "
             "labels are rule-derived. Findings are about the assurance method, not a real bank's "
             "data. (Set `substrate: csv` to ingest a real AMLSim run.)")
    L.append("- **Incentive is prompt-induced** in the core build (no fine-tuning); the organic "
             "fine-tuned organism is an extension.")
    _agree = validation.get("defensible_vs_truth_agreement")
    _agree_str = f" ({_agree * 100:.1f}% agreement here)" if _agree is not None else ""
    L.append(f"- **Evaluator is an LLM**, validated against ground truth{_agree_str}; agreement "
             "< 100% means it is a strong but not infallible verification layer.")
    L.append("- **Observability quality evals are LLM-judge** scores; the Phoenix integration logs "
             "real traces but the groundedness/coherence/hallucination signals are model-graded.")
    if run_meta["mode"] != "full":
        L.append(f"- This is a **{run_meta['mode']}** run (limit={run_meta.get('limit')}); robustness "
                 "across all seeds/phrasings is the `full` run.")
    L.append(f"- **Self-certification gap.** {SELF_CERT_GAP}")
    L.append("")
    L.append("See **`LIMITATIONS.md`** (model/eval card) for the full scope, out-of-scope list, "
             "and per-figure provenance. Regenerate with `uv run python -m tools.model_card`.")
    L.append("")
    return "\n".join(L)
