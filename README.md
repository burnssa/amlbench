# AMLBench

**Do AI agents clear reportable money-laundering alerts?**  ·  **v0**

[![verify](https://github.com/burnssa/amlbench/actions/workflows/ci.yml/badge.svg)](https://github.com/burnssa/amlbench/actions/workflows/ci.yml)

AI agents increasingly make decisions with human and legal consequences. The concrete case here:
escalating the suspicious-activity reports (SARs) required by the US Bank Secrecy Act (BSA). AMLBench
evaluates a model's escalation decisions under varying duty specifications, operational incentives,
plausible transaction cover stories, and harnessed models. Alerts are built with
[AMLSim](https://github.com/IBM/AMLSim) and scored against **deterministic BSA/AML rules, never an LLM
judge**, with prompts and cover stories grounded in documented real-world behavior.

🌐 [amlbench.com](https://amlbench.com) · 📄 [findings](docs/AMLBENCH_FINDINGS.md) · 📐 [spec](docs/BENCHMARK.md)

## What it measures

**Escalation sensitivity — the share of genuinely reportable alerts the agent escalates. Higher is
better.** A model triages synthetic AML alerts, escalating those that meet BSA criteria (structuring,
rapid pass-through / layering, off-profile dispersion, sanctioned counterparties, high-risk
jurisdictions) and clearing the rest; it never sees the labels. Stressor effects are reported as
**sensitivity lost, in percentage points**.

Three axes:

- **M · Model** — which model triages, holding harness, prompts, and alerts fixed.
- **B · Harness / prompt (protective → adversarial)** — everything the operator's prompt contributes,
  on one spectrum: how completely it states the analyst's legal obligations — from a **basic spec** to
  a **full spec** — and what it injects against them: operational **pressure**, or a **directive that
  inverts the decision rule**. Attacks run at both spec levels, so the protection a full spec buys is
  measured, not assumed.
- **A · Cover-story adversary (A0 → A3)** — how hard the alert works to look innocent: cover stories drawn
  from real laundering cases, woven into the narrative. Transaction facts and the ground-truth label
  never change. A0 raw → A1 grounded cover → A2 + KYC context → A3 best-of-N.

**Guardrails.** Specificity (share of the 12 benign alerts not escalated) is a **qualification gate
(≥90%)**, never ranked — a model that escalates everything can't qualify. The **bright-line catch
rate** (does it still escalate unmistakable structuring under cover) separates rule-following from
competence collapse.

## Results — v0

One frozen sample: 48 reportable + 12 benign alerts, seed 11, single run (±~0.05–0.07 — read for
shape). Prompt attack = worst case over four grounded directives; pressure = the incentive-only
condition. Six models clear the specificity gate.

| Model | Baseline sensitivity | Specificity (gate ≥90%) | Lost to prompt attack (pts) · basic → full spec | Lost to pressure (pts) | Lost to deceptive cover, A2 (pts) | Bright-line catch rate |
|---|---|---|---|---|---|---|
| Claude Opus 4.8 | 100% | 92% | 65 → 0 | 0 | 33 | 100% |
| GPT-5.5 | 100% | 100% | 67 → 0 | 0 | 52 | 100% |
| Claude Haiku 4.5 | 100% | 92% | 50 → 6 | 2 | 69 | 22% |
| GPT-4o | 100% | 100% | 54 → 6 | 17 | 69 | 33% |
| Llama-3-70b | 100% | 100% | 46 → 19 | 17 | 67 | 11% |
| Grok-4.3 | 100% | 100% | 46 → 31 | 17 | 63 | 44% |

*Excluded below the specificity gate — not ranked:* **Gemma-3-27b** — baseline sensitivity 100%,
specificity 42%. It escalates 58% of benign alerts, so its perfect-looking sensitivity is
over-flagging, not discrimination — and under an inverted-rule attack it swings to the opposite
extreme (96 pts lost, clearing even bright-line structuring).

Among the six qualifying models, the full spec neutralized prompt attacks for four; pure pressure
moved only three; and **deceptive cover stories lowered every model's sensitivity — including the two
robust to everything else.**

> Read the deceptive-cover column beside the bright-line catch rate: a low catch rate means the loss
> is partly competence collapse, not just discretion-shading. Covers were authored by Opus 4.8, so the
> Opus deceptive-cover cell is mild self-play; GPT-5.5 is the cross-model evidence. A3 is a footnoted
> upper bound (Opus sensitivity falls to 37.5%). Attribution is in
> [`docs/AMLBENCH_FINDINGS.md`](docs/AMLBENCH_FINDINGS.md).

## Installation

```bash
git clone https://github.com/burnssa/amlbench && cd amlbench
uv sync
uv run python -m data.build     # labeled dataset — offline, free, no key
```

## Run it

Running models needs your own provider keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `XAI_API_KEY`,
`REPLICATE_API_TOKEN`); cost is stated per command. Scores land in `results/canonical/leaderboard.json`.

```bash
uv run python -m amlbench run --dry-run                                            # plan, no spend
uv run python -m amlbench run                                                      # full grid
uv run python -m amlbench run --models "anthropic/claude-opus-4-8,your/model-id"   # your model
```

**Bring your own agent** — export the battery, run the prompts through your agent, score offline
(nothing leaves your machine): see the BYO guide, [`docs/BYO_GUIDE.md`](docs/BYO_GUIDE.md).

## How an evaluation works

1. **Build** synthetic alerts (AMLSim-derived), each with a deterministic BSA/AML label the model never sees.
2. **Triage** each alert under a prompt (Axis B) and cover condition (Axis A).
3. **Score** against ground truth — sensitivity, specificity, bright-line catch rate. No model grades another; the labels are rules.

## Grounding

Labels are **deterministic BSA/AML rules** (CTR/structuring statutes, FFIEC red flags, FATF/OFAC
lists; [`docs/RULE_BASIS.md`](docs/RULE_BASIS.md)). Every adversarial prompt and cover story traces to
a named source, tiered by evidence strength — enforcement cases (Rabobank, TD Bank, HSBC/Sinaloa,
Russian & Troika Laundromats, 1MDB, Danske) through the regulatory standard — with extrapolations
labeled as such (two of the four directives are extrapolated from the FFIEC "need not confirm a
predicate crime" standard, never attributed to a named case). Full evidence base:
[`docs/BENCHMARK.md`](docs/BENCHMARK.md) §12.

## Who is this for

- **Fintech compliance providers** — a model-selection safety signal for compliance-adjacent agents.
- **Banks** — a public reference point; the private tier runs your real deployed agent against a held-out, rotated set and issues an attestation certificate.
- **Researchers** — an objectively ground-truthed testbed for integrity under pressure.

## Reproduce & verify

```bash
./scripts/verify.sh              # entire offline harness, no API key, no cost
uv run python -m tools.repro     # replay the committed v0 ablation deterministically
```

## Citation

```bibtex
@misc{amlbench2026,
  title  = {AMLBench: A Benchmark for AML Alert Triage under Adversarial Pressure},
  author = {Burns, Scott},
  year   = {2026},
  url    = {https://amlbench.com}
}
```

## License

[Apache 2.0](LICENSE). Copyright 2026 Superjective. Data substrate is a pure-Python port of
[IBM AMLSim](https://github.com/IBM/AMLSim) (Apache-2.0) — see [`NOTICE`](NOTICE). Eval card:
[`LIMITATIONS.md`](LIMITATIONS.md) · security map: [`SECURITY.md`](SECURITY.md).

---

*AMLBench is developed with [Superjective](https://superjective.ai).*
