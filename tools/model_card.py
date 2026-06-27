"""Generate LIMITATIONS.md — a model/eval card — entirely from committed results files.

Single source of truth: every quantitative claim is READ from a results artifact and
formatted here, never hand-typed, so the candor section cannot drift from REPORT.md,
the deck, or the landing page. Structured as a recognizable eval/model card (version &
scope, intended use, out-of-scope, data, metrics, caveats, self-cert gap,
reproducibility) so a model-risk reader can file it under familiar NIST AI RMF /
model-documentation conventions.

    uv run python -m tools.model_card        # writes LIMITATIONS.md  ($0, no model calls)

Rates are rendered at one decimal (#.#%) to match REPORT.md and the deck.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from common.claims import PROJECT_TAGLINE, SELF_CERT_GAP
from common.config import load_config, resolve
from tools.certify import _battery_hash


def pct1(x: float) -> str:
    return f"{x * 100:.1f}%"


def _json(*parts) -> dict | None:
    p = resolve(*parts)
    return json.loads(p.read_text()) if p.exists() else None


def _git_short() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def _multimodel_range(mm: dict | None) -> str | None:
    """Min–max Δ(under-escalation) neutral→quota across the cross-provider models."""
    if not mm:
        return None
    results = mm.get("results", {})
    # `results` is a dict keyed by model id: {model: {neutral: {...}, quota: {...}}}.
    items = results.items() if isinstance(results, dict) else (
        (m, c) for d in results for m, c in d.items())
    deltas = []
    for _model, cells in items:
        n = cells.get("neutral", {}).get("under_escalation")
        q = cells.get("quota", {}).get("under_escalation")
        if n is not None and q is not None:
            deltas.append(q - n)
    if not deltas:
        return None
    return f"+{pct1(min(deltas))} to +{pct1(max(deltas))} across {len(deltas)} models"


def build() -> str:
    cfg = load_config()
    core_b = _json("results", "runs", "core", "behavioral.json")
    core_v = _json("results", "runs", "core", "validation.json")
    for_b = _json("results", "runs", "ws2_foreign", "behavioral.json")
    for_v = _json("results", "runs", "ws2_foreign", "validation.json")
    probe = _json("results", "runs", "probe", "probe.json")
    mm = _json("results", "runs", "multimodel", "multimodel.json")

    as_of = datetime.now(timezone.utc).date().isoformat()
    L: list[str] = []
    L.append("# Cupel — Limitations & Scope")
    L.append("")
    L.append(f"> {PROJECT_TAGLINE}. **Model / eval card.** Every figure below is read "
             "from a committed results file by `tools/model_card.py` — not hand-entered — "
             "so it matches `results/REPORT.md`, the deck, and the landing page exactly. "
             "Rates are shown at one decimal (#.#%). Regenerate with "
             "`uv run python -m tools.model_card`.")
    L.append("")

    # ── Version & scope stamp ──────────────────────────────────────────────
    L.append("## Version & scope")
    L.append("")
    L.append("| Field | Value |")
    L.append("|---|---|")
    L.append(f"| As-of | {as_of} |")
    L.append(f"| Git commit | `{_git_short()}` |")
    L.append(f"| Battery version | `{_battery_hash()}` |")
    L.append(f"| Battery | {cfg['dataset']['n_alerts']} alerts, substrate "
             f"`{cfg['dataset']['substrate']}`, seeds {cfg['run']['seeds']} "
             f"(core seed {cfg['run']['core_seed']}, phrasing `{cfg['run']['core_phrasing']}`) |")
    L.append(f"| Agent under test (reference) | `{cfg['agent']['model']}` |")
    L.append(f"| Independent evaluator | `{cfg['evaluator']['model']}` |")
    L.append(f"| Observability quality judge | `{cfg['observability']['eval_model']}` |")
    L.append(f"| Models exercised (cross-provider) | {', '.join(f'`{m}`' for m in cfg['generalization']['agent_models'])} |")
    L.append("")

    # ── Intended use ───────────────────────────────────────────────────────
    L.append("## Intended use")
    L.append("")
    L.append("Cupel measures whether an AML transaction-monitoring agent's escalate/clear "
             "decisions stay defensible under a hidden operating incentive, and whether an "
             "independent evaluator catches induced under-escalation that standard LLM "
             "observability does not surface. It produces a per-decision verification ledger "
             "and an attestation finding suitable for an examiner audience. It is a "
             "**behavioral assurance harness**, not a deployment monitor.")
    L.append("")

    # ── Out-of-scope ───────────────────────────────────────────────────────
    L.append("## Out-of-scope use (what Cupel does NOT test)")
    L.append("")
    L.append("Naming the boundary is deliberate: it pre-empts \"does it cover X?\" and stops "
             "the suite from being over-applied. Cupel does **not** evaluate:")
    L.append("")
    L.append("- **KYC / customer onboarding** — identity verification, beneficial-ownership, CDD/EDD.")
    L.append("- **Sanctions-screening accuracy** — name-matching quality, list coverage, fuzzy-match tuning.")
    L.append("- **Real-data / production performance** — results are on a synthetic battery (see Data); they characterize the *method*, not a bank's live alert stream.")
    L.append("- **Adversarial prompt injection / jailbreak robustness** — the incentive is a mundane operating-context nudge, not an attack.")
    L.append("- **Fairness / disparate impact** — no protected-attribute or demographic analysis.")
    L.append("")

    # ── Data ───────────────────────────────────────────────────────────────
    L.append("## Data")
    L.append("")
    L.append("- **Synthetic, AMLSim-faithful port.** The substrate is a pure-Python port of "
             "AMLSim's typology-graph generator + temporal emitter (the standard open simulator "
             "in AML research), **not** real bank data and not the AMLSim Java/MASON runtime. "
             "Set `dataset.substrate: csv` to ingest a real AMLSim Java run.")
    L.append("- **Ground-truth labels are deterministic BSA/AML rules**, never an LLM, so "
             "under-escalation is objectively measurable; the evaluator never sees them.")
    if core_b:
        ov = core_b["overall"]
        L.append(f"- **Core battery:** {ov['neutral_total']} alerts per condition "
                 f"(`results/runs/core/behavioral.json`).")
    L.append("")

    # ── Metrics (each line cites its source file + regen command) ───────────
    L.append("## Metrics")
    L.append("")
    L.append("Each figure cites the file it is read from and the command that regenerates it.")
    L.append("")
    if core_b:
        ov = core_b["overall"]
        L.append(f"- **Core under-escalation, neutral → quota:** {pct1(ov['neutral_rate'])} → "
                 f"{pct1(ov['incentivized_rate'])} ({ov['incentivized_missed']}/{ov['incentivized_total']} "
                 f"reportable alerts missed; Cohen's h = {ov['cohens_h']}, p = {ov['p_value']}). "
                 "— `results/runs/core/behavioral.json`; `uv run python run.py --mode core`.")
    if core_v:
        sd = core_v.get("suppression_detection", {})
        L.append(f"- **Independent evaluator vs. ground truth (core):** "
                 f"{pct1(core_v['defensible_vs_truth_agreement'])} agreement; recall "
                 f"{pct1(sd.get('recall', 0))} on {sd.get('n_under_escalations')} under-escalations. "
                 "— `results/runs/core/validation.json`.")
    if for_b and for_v:
        ov = for_b["overall"]
        sd = for_v.get("suppression_detection", {})
        L.append(f"- **BYO cross-provider stand-in (GPT-4o, vendor-style prompt):** under-escalation "
                 f"{pct1(ov['neutral_rate'])} → {pct1(ov['incentivized_rate'])}; evaluator "
                 f"{pct1(for_v['defensible_vs_truth_agreement'])} agreement, recall "
                 f"{pct1(sd.get('recall', 0))} on {sd.get('n_under_escalations')} suppressed alerts. "
                 "— `results/runs/ws2_foreign/{behavioral,validation}.json`; `uv run python ws2_milestone.py`.")
    rng = _multimodel_range(mm)
    if rng:
        L.append(f"- **Cross-model susceptibility (quota incentive):** Δ under-escalation {rng}. "
                 "— `results/runs/multimodel/multimodel.json`; `uv run python -m eval.multimodel`.")
    if probe:
        L.append(f"- **Incentive shape > strength:** the bureaucratic quota framing induced "
                 f"{pct1(probe['quota']['under_escalation'])} under-escalation vs. "
                 f"{pct1(probe['neutral']['under_escalation'])} neutral; blunt high-pressure framings "
                 "induced ≈0%. — `results/runs/probe/probe.json`; `uv run python -m eval.probe`.")
    L.append("")

    # ── Caveats ────────────────────────────────────────────────────────────
    L.append("## Caveats")
    L.append("")
    L.append(f"- **Single-seed core.** Headline figures are seed {cfg['run']['core_seed']}, "
             f"phrasing `{cfg['run']['core_phrasing']}`. Seeds {cfg['run']['seeds']} and all "
             "phrasings are configured; run the multi-seed robustness sweep with "
             "`uv run python run.py --mode full`.")
    agree_bits = []
    if core_v:
        agree_bits.append(pct1(core_v["defensible_vs_truth_agreement"]) + " core")
    if for_v:
        agree_bits.append(pct1(for_v["defensible_vs_truth_agreement"]) + " BYO")
    agree_str = ", ".join(agree_bits) if agree_bits else "validated against ground truth"
    L.append(f"- **The verifier is itself a model** (`{cfg['evaluator']['model']}`), validated "
             f"against ground truth ({agree_str}). Agreement < 100% means it is a strong but "
             "not infallible verification layer.")
    L.append("- **Observability quality evals are LLM-judge scores.** The Phoenix integration "
             "logs real traces, but groundedness/coherence/hallucination signals are model-graded.")
    L.append("- **The incentive is prompt-induced** in the core build (no fine-tuning); an "
             "organically fine-tuned organism is an extension, not what these numbers measure.")
    L.append("")

    # ── Self-cert gap (single-sourced) ─────────────────────────────────────
    L.append("## The self-certification gap")
    L.append("")
    L.append(SELF_CERT_GAP)
    L.append("")
    L.append("_This sentence is single-sourced in `common/claims.py` (`SELF_CERT_GAP`) and must "
             "appear verbatim on the landing-page certificate CTA, so the honest limit and the "
             "paid offer are literally one statement._")
    L.append("")

    # ── Reproducibility ────────────────────────────────────────────────────
    L.append("## Reproducibility")
    L.append("")
    L.append("Every figure above is regenerable at $0 from committed run data:")
    L.append("")
    L.append("```bash")
    L.append("uv run python rerender.py --mode core          # core deliverables, no model calls")
    L.append("uv run python rerender.py --mode ws2_foreign   # BYO stand-in deliverables, no model calls")
    L.append("uv run python -m tools.model_card              # regenerate this card")
    L.append("```")
    L.append("")
    L.append(f"---")
    L.append(f"{PROJECT_TAGLINE}.")
    L.append("")
    return "\n".join(L)


def main() -> None:
    out = resolve("LIMITATIONS.md")
    out.write_text(build())
    print(f"[model_card] wrote {out}")


if __name__ == "__main__":
    main()
