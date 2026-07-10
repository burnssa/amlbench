# AMLBench — Limitations & Scope

> **Model / eval card.** Every figure below is read from a committed results file by `tools/model_card.py` — not hand-entered — so it matches `results/REPORT.md`, the deck, and the landing page exactly. Rates are shown at one decimal (#.#%). Regenerate with `uv run python -m tools.model_card`.

> **Scope note.** The Metrics section below reports the **v0 exploratory ablation** (the prompt-attack surface, single reference model + a small cross-provider ladder). The **authoritative** current results are the canonical run — all panel models over both attack surfaces — in [`docs/AMLBENCH_FINDINGS.md`](docs/AMLBENCH_FINDINGS.md) + `results/canonical/leaderboard.json`. Where the v0 figures credit a *peer-benchmark incentive*, read the ablation caveat: the active ingredient is the embedded judgment-inversion *directive* (a prompt attack, patchable by a full spec), not the incentive, which is ~0 on the frontier.

## Version & scope

| Field | Value |
|---|---|
| As-of | 2026-07-10 |
| Git commit | `79e9959` |
| Battery version | `sha256:604eb3a04b6ef722` |
| Battery | 240 alerts, substrate `amlsim_port`, seeds [11, 23, 42] (core seed 11, phrasing `quota`) |
| Agent under test (reference) | `claude-sonnet-4-6` |
| Independent evaluator | `claude-opus-4-8` |
| Observability quality judge | `claude-haiku-4-5-20251001` |
| Models exercised (cross-provider) | `claude-opus-4-8`, `claude-haiku-4-5-20251001`, `gpt-5.5`, `gpt-4o`, `replicate/google-deepmind/gemma-3-27b-it`, `replicate/meta/meta-llama-3-70b-instruct`, `xai/grok-4.3` |

## Intended use

AMLBench measures whether an AML transaction-monitoring agent keeps its escalate/clear judgment when the task is made adversarial — across the **prompt-attack surface** (judgment-inversion directives + operational incentives, defended by a complete spec) and the **data-attack surface** (grounded launderer cover stories that survive a complete spec) — scored against deterministic BSA/AML ground truth. The private tier additionally produces a per-decision verification ledger and attestation finding for an examiner audience. It is a **benchmark + behavioral assurance harness**, not a deployment monitor.

## Out-of-scope use (what AMLBench does NOT test)

Naming the boundary is deliberate: it pre-empts "does it cover X?" and stops the suite from being over-applied. AMLBench does **not** evaluate:

- **KYC / customer onboarding** — identity verification, beneficial-ownership, CDD/EDD.
- **Sanctions-screening accuracy** — name-matching quality, list coverage, fuzzy-match tuning.
- **Real-data / production performance** — results are on a synthetic battery (see Data); they characterize the *method*, not a bank's live alert stream.
- **Adversarial prompt injection / jailbreak robustness** — the prompt attacks are plausible operating-context framings (directives, incentives), not token-level injection or jailbreaks; the data attack is a plausible cover story, not a malformed payload.
- **Fairness / disparate impact** — no protected-attribute or demographic analysis.

## Data

- **Synthetic, AMLSim-faithful port.** The substrate is a pure-Python port of AMLSim's typology-graph generator + temporal emitter (the standard open simulator in AML research), **not** real bank data and not the AMLSim Java/MASON runtime. Fidelity (schema, cash/non-cash split, type vocabulary, typology graph shapes, SAR labeling) is checked against AMLSim's real committed sample output — see [`results/AMLSIM_FIDELITY.md`](results/AMLSIM_FIDELITY.md). Direct `dataset.substrate: csv` ingestion of a real AMLSim run is a planned seam, currently stubbed.
- **Ground-truth labels are deterministic BSA/AML rules**, never an LLM, so under-escalation is objectively measurable; the evaluator never sees them. Each rule's statutory / supervisory basis is documented in [`docs/RULE_BASIS.md`](docs/RULE_BASIS.md).
- **Core battery:** 60 alerts per condition (`results/runs/core/behavioral.json`).

## Metrics

Each figure cites the file it is read from and the command that regenerates it.

- **Core under-escalation, neutral → peer benchmark:** 0.0% → 31.7% (19/60 reportable alerts missed; Cohen's h = 1.195, p = 0.0). — `results/runs/core/behavioral.json`; `uv run python run.py --mode core`.
- **Independent evaluator vs. ground truth (core):** 88.3% agreement; recall 100.0% on 19 under-escalations. — `results/runs/core/validation.json`.
- **BYO cross-provider stand-in (GPT-4o, vendor-style prompt):** under-escalation 13.3% → 60.0%; evaluator 92.2% agreement, recall 100.0% on 44 suppressed alerts. — `results/runs/ws2_foreign/{behavioral,validation}.json`; `uv run python ws2_milestone.py`.
- **Cross-model `quota` ladder (5 models) [v0 — see ablation caveat]:** the `quota` framing induces **33.3%–56.7%** under-escalation across every model tested, including the flagship. **But `quota` bundled an incentive with a judgment-inversion directive; the ablation + canonical run attribute the effect to the directive (a prompt attack, patched by a full spec), not the incentive (~0 on the frontier).** Blunt high-pressure framings stay in the single digits in only 2 of 5 models (the most capable Claude); the others bend to blunt pressure too (up to 100%). — `results/runs/ladder_5model/multimodel.json`; `uv run python -m eval.multimodel` + `eval.ladder_multimodel`.
- **Incentive shape vs. strength (single model, Claude Sonnet 4.6):** the peer-benchmark framing induced 31.7% under-escalation vs. 0.0% neutral, while blunt high-pressure framings induced ≈0%. **This 'shape beats strength' pattern is specific to the most capable models** — weaker and cross-provider models also bend to blunt pressure (see the ladder above). — `results/runs/probe/probe.json`; `uv run python -m eval.probe`.

## Caveats

- **Single-seed core.** Headline figures are seed 11, phrasing `quota`. Seeds [11, 23, 42] and all phrasings are configured; run the multi-seed robustness sweep with `uv run python run.py --mode full`.
- **The verifier is itself a model** (`claude-opus-4-8`), validated against ground truth (88.3% core, 92.2% BYO). Agreement < 100% means it is a strong but not infallible verification layer.
- **Observability quality evals are LLM-judge scores.** The Phoenix integration logs real traces, but groundedness/coherence/hallucination signals are model-graded.
- **The incentive is prompt-induced** in the core build (no fine-tuning); an organically fine-tuned organism is an extension, not what these numbers measure.

## The self-certification gap

A self-run AMLBench certificate attests only that the harness scored these decisions against a synthetic ground-truth battery; it cannot prove the customer pointed it at their real production agent. Closing that gap — by having us drive the agent ourselves — is the purpose of paid independent attestation.

_This sentence is single-sourced in `common/claims.py` (`SELF_CERT_GAP`) and must appear verbatim on the landing-page certificate CTA, so the honest limit and the paid offer are literally one statement._

## Reproducibility

Every figure above is regenerable at $0 from committed run data:

```bash
uv run python rerender.py --mode core          # core deliverables, no model calls
uv run python rerender.py --mode ws2_foreign   # BYO stand-in deliverables, no model calls
uv run python -m tools.model_card              # regenerate this card
```
