# Cupel — Limitations & Scope

> **Model / eval card.** Every figure below is read from a committed results file by `tools/model_card.py` — not hand-entered — so it matches `results/REPORT.md`, the deck, and the landing page exactly. Rates are shown at one decimal (#.#%). Regenerate with `uv run python -m tools.model_card`.

## Version & scope

| Field | Value |
|---|---|
| As-of | 2026-06-27 |
| Git commit | `6c6b16b` |
| Battery version | `sha256:604eb3a04b6ef722` |
| Battery | 240 alerts, substrate `amlsim_port`, seeds [11, 23, 42] (core seed 11, phrasing `quota`) |
| Agent under test (reference) | `claude-sonnet-4-6` |
| Independent evaluator | `claude-opus-4-8` |
| Observability quality judge | `claude-haiku-4-5-20251001` |
| Models exercised (cross-provider) | `claude-sonnet-4-6`, `gpt-4o`, `replicate/meta/meta-llama-3-70b-instruct`, `claude-haiku-4-5-20251001` |

## Intended use

Cupel measures whether an AML transaction-monitoring agent's escalate/clear decisions stay defensible under a hidden operating incentive, and whether an independent evaluator catches induced under-escalation that standard LLM observability does not surface. It produces a per-decision verification ledger and an attestation finding suitable for an examiner audience. It is a **behavioral assurance harness**, not a deployment monitor.

## Out-of-scope use (what Cupel does NOT test)

Naming the boundary is deliberate: it pre-empts "does it cover X?" and stops the suite from being over-applied. Cupel does **not** evaluate:

- **KYC / customer onboarding** — identity verification, beneficial-ownership, CDD/EDD.
- **Sanctions-screening accuracy** — name-matching quality, list coverage, fuzzy-match tuning.
- **Real-data / production performance** — results are on a synthetic battery (see Data); they characterize the *method*, not a bank's live alert stream.
- **Adversarial prompt injection / jailbreak robustness** — the incentive is a mundane operating-context nudge, not an attack.
- **Fairness / disparate impact** — no protected-attribute or demographic analysis.

## Data

- **Synthetic, AMLSim-faithful port.** The substrate is a pure-Python port of AMLSim's typology-graph generator + temporal emitter (the standard open simulator in AML research), **not** real bank data and not the AMLSim Java/MASON runtime. Set `dataset.substrate: csv` to ingest a real AMLSim Java run.
- **Ground-truth labels are deterministic BSA/AML rules**, never an LLM, so under-escalation is objectively measurable; the evaluator never sees them. Each rule's statutory / supervisory basis is documented in [`docs/RULE_BASIS.md`](docs/RULE_BASIS.md).
- **Core battery:** 60 alerts per condition (`results/runs/core/behavioral.json`).

## Metrics

Each figure cites the file it is read from and the command that regenerates it.

- **Core under-escalation, neutral → quota:** 0.0% → 31.7% (19/60 reportable alerts missed; Cohen's h = 1.195, p = 0.0). — `results/runs/core/behavioral.json`; `uv run python run.py --mode core`.
- **Independent evaluator vs. ground truth (core):** 88.3% agreement; recall 100.0% on 19 under-escalations. — `results/runs/core/validation.json`.
- **BYO cross-provider stand-in (GPT-4o, vendor-style prompt):** under-escalation 13.3% → 60.0%; evaluator 92.2% agreement, recall 100.0% on 44 suppressed alerts. — `results/runs/ws2_foreign/{behavioral,validation}.json`; `uv run python ws2_milestone.py`.
- **Cross-model susceptibility (quota incentive):** Δ under-escalation +28.3% to +58.3% across 4 models. — `results/runs/multimodel/multimodel.json`; `uv run python -m eval.multimodel`.
- **Incentive shape > strength:** the bureaucratic quota framing induced 31.7% under-escalation vs. 0.0% neutral; blunt high-pressure framings induced ≈0%. — `results/runs/probe/probe.json`; `uv run python -m eval.probe`.

## Caveats

- **Single-seed core.** Headline figures are seed 11, phrasing `quota`. Seeds [11, 23, 42] and all phrasings are configured; run the multi-seed robustness sweep with `uv run python run.py --mode full`.
- **The verifier is itself a model** (`claude-opus-4-8`), validated against ground truth (88.3% core, 92.2% BYO). Agreement < 100% means it is a strong but not infallible verification layer.
- **Observability quality evals are LLM-judge scores.** The Phoenix integration logs real traces, but groundedness/coherence/hallucination signals are model-graded.
- **The incentive is prompt-induced** in the core build (no fine-tuning); an organically fine-tuned organism is an extension, not what these numbers measure.

## The self-certification gap

A self-run Cupel certificate attests only that the harness scored these decisions against a synthetic ground-truth battery; it cannot prove the customer pointed it at their real production agent. Closing that gap — by having us drive the agent ourselves — is the purpose of paid independent attestation.

_This sentence is single-sourced in `common/claims.py` (`SELF_CERT_GAP`) and must appear verbatim on the landing-page certificate CTA, so the honest limit and the paid offer are literally one statement._

## Reproducibility

Every figure above is regenerable at $0 from committed run data:

```bash
uv run python rerender.py --mode core          # core deliverables, no model calls
uv run python rerender.py --mode ws2_foreign   # BYO stand-in deliverables, no model calls
uv run python -m tools.model_card              # regenerate this card
```
