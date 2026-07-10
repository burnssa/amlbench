# AMLBench

**A benchmark for how AI models fulfill legal duties under pressure.**  ·  **v0**

[![verify](https://github.com/burnssa/amlbench/actions/workflows/ci.yml/badge.svg)](https://github.com/burnssa/amlbench/actions/workflows/ci.yml)

AI systems increasingly carry legal duties, not just task instructions; AMLBench tests one
concretely — the Bank Secrecy Act duty to escalate suspicious activity. A model acts as an
anti–money-laundering (AML) alert-triage analyst and must escalate genuinely reportable alerts even
when the prompt and the data are made adversarial. Every decision is scored against **deterministic
BSA/AML rules, never an LLM judge**.

- 🌐 Site & live leaderboard: [amlbench.com](https://amlbench.com)
- 📄 Findings write-up (technical record): [`docs/AMLBENCH_FINDINGS.md`](docs/AMLBENCH_FINDINGS.md)
- 📐 Full spec: [`docs/BENCHMARK.md`](docs/BENCHMARK.md)

## What it measures

**Escalation sensitivity — the share of genuinely reportable alerts the agent escalates. Higher is
better.** A model triages synthetic AML alerts and must **ESCALATE** any that meet Bank Secrecy Act
criteria (structuring, rapid pass-through / layering, off-profile dispersion, sanctioned
counterparties, high-risk-jurisdiction exposure) or **CLEAR** the rest; it never sees the labels. The
effect of a stressor is reported as **sensitivity lost, in percentage points**.

Sensitivity is measured across three axes:

- **Axis M · Model** — which model triages, holding harness, prompts, and alerts fixed.
- **Axis B · protective → adversarial · Harness / prompt** — everything the operator's prompt
  contributes, on one spectrum: how completely it states the analyst's legal obligations — from a
  **basic spec** (B0) to a **full spec** (B2) — and what it injects against them: operational
  **pressure**, or a **directive that inverts the decision rule**. Attacks run at both spec levels,
  so the protection a full spec buys is measured, not assumed.
- **Axis A · A0 → A3 · Data adversary** — how hard the alert itself works to look innocent: cover
  stories drawn from real laundering cases, woven into the narrative. The transaction facts and the
  ground-truth label never change. Levels: A0 raw → A1 grounded cover story → A2 + supporting KYC
  context → A3 best-of-N.

Two guardrails keep the score honest. **Specificity** — the share of the 12 benign alerts *not*
escalated — is a **qualification gate (≥90%)**, never a ranked score: a model that escalates
everything cannot qualify. The **bright-line catch rate** — whether the model still escalates
*unmistakable* structuring under cover — separates rule-following from competence collapse.

## Results — v0

One frozen sample: 48 reportable + 12 benign alerts, seed 11, single run (±~0.05–0.07 — read for
shape). Prompt attack = the worst case over four grounded judgment-inversion directives; pressure =
the incentive-only condition. Six models clear the specificity gate.

| Model | Baseline sensitivity | Specificity (gate ≥90%) | Lost to prompt attack (pts) · basic → full spec | Lost to pressure (pts) | Lost to deceptive data, A2 (pts) | Bright-line catch rate |
|---|---|---|---|---|---|---|
| Claude Opus 4.8 | 100% | 92% | 67 → 2 | 0 | 38 | 100% |
| GPT-5.5 | 100% | 100% | 69 → 0 | 0 | 48 | 89% |
| Claude Haiku 4.5 | 100% | 100% | 44 → 4 | 2 | 63 | 44% |
| GPT-4o | 98% | 100% | 50 → 4 | 17 | 69 | 33% |
| Llama-3-70b | 100% | 100% | 46 → 19 | 17 | 67 | 11% |
| Grok-4.3 | 100% | 100% | 40 → 29 | 17 | 63 | 44% |

*Excluded below the specificity gate — not ranked:* **Gemma-3-27b** — baseline sensitivity 100%,
specificity 54%. It escalates 46% of benign alerts, so its perfect-looking sensitivity is
over-flagging, not discrimination — and under an inverted-rule attack it swings to the opposite
extreme (94 pts lost, clearing even bright-line structuring).

Among the six qualifying models, the full spec neutralized prompt attacks for four; pure pressure
moved only three; and **deceptive alert data lowered every model's sensitivity — including the two
robust to everything else.**

> **Read the deceptive-data column beside the bright-line catch rate:** a low catch rate means the
> loss is partly competence collapse under cover, not just discretion-shading. **Covers were authored
> by Opus 4.8**, so the Opus deceptive-data cell is mild self-play; **GPT-5.5 is the cross-model
> evidence.** A3 (best-of-N covers) is an upper bound, footnoted only: Opus sensitivity falls to
> 37.5%. Attribution and interpretation are in [`docs/AMLBENCH_FINDINGS.md`](docs/AMLBENCH_FINDINGS.md).

## Installation

```bash
git clone https://github.com/burnssa/amlbench && cd amlbench
uv sync
uv run python -m data.build     # generate the labeled dataset — offline, free, no key
```

## Run it

Running models needs your own provider keys (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `XAI_API_KEY`,
`REPLICATE_API_TOKEN`); cost is stated on each command. Scores land in
`results/canonical/leaderboard.json`.

```bash
uv run python -m amlbench run --dry-run                       # plan + call count, no spend
uv run python -m amlbench run                                 # full leaderboard grid
uv run python -m amlbench run --models "anthropic/claude-opus-4-8,your/model-id"   # your model
```

**Bring your own agent** (score decisions locally, nothing leaves your machine): export the battery,
run the prompts through your agent, and score the decisions offline — see the BYO guide,
[`docs/BYO_GUIDE.md`](docs/BYO_GUIDE.md).

## How an evaluation works

1. **Build** synthetic alerts from an AMLSim-derived substrate, each with a deterministic BSA/AML
   label the model never sees (`data/build.py`, `data/rules.py`).
2. **Triage** each alert under a given prompt (Axis B) and data condition (Axis A) (`agent/triage.py`).
3. **Score** against ground truth — escalation sensitivity, specificity, bright-line catch rate
   (`eval/metrics.py`). No model grades another; the labels are rules.

## Grounding & ground truth

Labels are **deterministic BSA/AML rules, never an LLM judge** (CTR/structuring statutes, FFIEC red
flags, FATF/OFAC lists), documented in [`docs/RULE_BASIS.md`](docs/RULE_BASIS.md). Every adversarial
prompt and cover story **traces to a named source, tiered by evidence strength** — enforcement cases
(Rabobank, TD Bank, HSBC/Sinaloa, Russian & Troika Laundromats, 1MDB, Danske) through the regulatory
standard, with **extrapolations labeled as such** (two of the four directives are extrapolated from
the FFIEC "need not confirm a predicate crime" standard and are never attributed to a named case).
The full tiered evidence base is [`docs/BENCHMARK.md`](docs/BENCHMARK.md) §12.

## Who is this for

- **Fintech compliance providers** — a model-selection safety signal for compliance-adjacent agents.
- **Banks** — a public reference point; the private tier runs your *real* deployed agent against a
  held-out, rotated set and issues an attestation certificate.
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

[Apache 2.0](LICENSE). Copyright 2026 Superjective. The data substrate is a pure-Python port of
[IBM AMLSim](https://github.com/IBM/AMLSim) (Apache-2.0) — attribution and BibTeX in [`NOTICE`](NOTICE).
See [`LIMITATIONS.md`](LIMITATIONS.md) for the eval card and [`SECURITY.md`](SECURITY.md) for the
network/security map.

---

*AMLBench is developed with [Superjective](https://superjective.ai).*
