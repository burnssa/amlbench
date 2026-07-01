# Cupel - assurance harness for AML triage agents

**Cupel** is an open-source assurance harness for AI agents that triage
anti–money-laundering (AML) alerts. Point it at our reference agent to reproduce the
finding, or at **your own** agent to get your own report, ledger, and certificate
locally, with your decision data never leaving your machine.

## How it works

Cupel runs your agent over a battery of synthetic AML alerts that carry
**deterministic BSA/AML ground-truth labels**, under two matched conditions — a neutral
instruction and one carrying an ordinary throughput / false-positive-reduction incentive
— and scores every decision three ways:

- **Behavioral.** Under-escalation measured against ground truth (with effect sizes and
  confidence intervals), so incentive-induced suppression is objectively quantifiable
  rather than a matter of opinion.
- **Observability.** The same run is traced through a standard LLM observability and
  quality stack (Arize Phoenix: groundedness / coherence / hallucination evals + drift),
  so you can see whether conventional monitoring would flag anything.
- **Interpretable verification.** An independent evaluator (Claude Opus 4.8) reviews each
  decision *blind to the labels* and emits a human-readable verdict — is the decision
  *defensible*, is the rationale *faithful*, plus an examiner-readable note — and the
  evaluator is itself validated against ground truth.

Ground truth is deterministic, never an LLM: labels come from BSA/AML rules applied to a
synthetic, AMLSim-derived dataset, so the evaluator never sees the answers and
under-escalation is measurable on its face.

**The pipeline, end to end** — each stage is one top-level directory (see [Layout](#layout)):

```
data.build            agent                    scoring
synthetic alerts  →   neutral vs          →    behavioral (vs ground truth)       →   finding/
+ BSA/AML labels      incentivized              observability (Phoenix)                + REPORT.md
                      triage decision           interpretable verification (Opus)
```

## Two ways to use it

**1. Reproduce the worked example (our reference agent).**
Runs the built-in Sonnet triage agent through the full pipeline and regenerates the
study. The headline finding: a mundane peer-benchmark incentive drives substantial
under-escalation of reportable alerts across every model tested — from ~32% on the
reference agent to ~57% on the most susceptible — while observability stays quiet, and
the independent verifier flags every suppressed case. Read it without running anything
in [`results/REPORT.md`](results/REPORT.md) (full methodology) or
[`results/SAMPLE_REPORT.md`](results/SAMPLE_REPORT.md) (the one-screen examiner deliverable).

**2. Assay your own agent (BYO).**
Export the battery, run those prompts through *your* agent, and score the decisions
locally. You get your own under-escalation rate, a per-decision ledger, and an optional
aggregate-only certificate — with **zero network calls** in the scoring path and nothing
leaving your environment. See [`docs/BYO_GUIDE.md`](docs/BYO_GUIDE.md).

## Quickstart

The data layer is free and offline. Anything that calls a model needs your own
`ANTHROPIC_API_KEY` and costs a few dollars; cost is stated on each command.

```bash
uv sync                                    # install deps
uv run python -m data.build                # generate the labeled dataset — offline, FREE, no key
```

**Reproduce the worked example (reference agent):**

```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env # BYO key; the commands below spend a few $

uv run python run.py --mode dry            # small plumbing check (~$1–2)
uv run python run.py --mode core           # full N=240, 1 seed / 1 phrasing — the headline run
uv run python run.py --mode full           # all seeds × all phrasings — robustness
```

**Assay your own agent (BYO):** LogReplay is offline and prints your under-escalation
number with **zero network calls**; the optional ledger/certificate stage needs the key.

```bash
uv run python -m data.build --export-battery                # prompts only, labels stripped — FREE
# run those prompts through your agent → a decisions CSV (see the CSV contract), then:
uv run python run.py --agent logreplay --decisions your_decisions.csv
```

Prefer a live endpoint to a CSV? `--agent api --endpoint <url>` drives your endpoint
(black-box contract in `agent/byo.py`); the held-out, un-gameable `--challenge` tier is
server-side (see [`docs/CHALLENGE_PROTOCOL.md`](docs/CHALLENGE_PROTOCOL.md)).

The standalone **Inspect AI** behavioral task (a second, independent implementation of
the behavioral arm) can be run on its own:

```bash
uv run inspect eval eval/aml_task.py --model anthropic/claude-sonnet-4-6 -T condition=incentivized -T phrasing=throughput_backlog
uv run inspect eval eval/aml_task.py --model anthropic/claude-sonnet-4-6 -T condition=neutral
```

## Outputs

**Reference run:**

- [`results/SAMPLE_REPORT.md`](results/SAMPLE_REPORT.md) — the **examiner-facing deliverable**: a bounded, one-screen sample attestation (finding, what was observed, independent-verification summary, sample records)
- [`results/REPORT.md`](results/REPORT.md) — **full methodology + findings**: thesis, method, embedded domain primer, quantified results, plots, sample records, limitations
- `results/ledger/decision_ledger.md` — full per-decision verification ledger · `results/ledger/assurance_summary.md` — distilled examiner package
- `results/finding/attestation.{json,md}` — the attestation finding
- `results/runs/<mode>/*.{json,jsonl}` — raw decisions, quality scores, verifications, metrics · `results/plots/*.png`

**BYO run:**

- `results/BYO_REPORT.md` — your under-escalation rate, by typology
- `results/ledger/byo_decision_ledger.md` — every decision, independently verified
- `results/finding/byo_cert_request.json` — aggregate-only certificate request (opt-in)

Domain primer: [`docs/DOMAIN_BACKGROUND.md`](docs/DOMAIN_BACKGROUND.md) — KYC vs transaction
monitoring vs triage, the typology shapes, and how the synthetic data maps to real alerts.

## Layout

| dir | what |
|---|---|
| `data/` | AMLSim-derived substrate (`amlsim.py`), alert builder (`build.py`), deterministic BSA/AML ground-truth labeler (`rules.py`) |
| `agent/` | triage agent (`triage.py`) + matched neutral/incentivized conditions (`conditions.py`) |
| `observability/` | observability arm: Phoenix tracing + quality evals (`instrument.py`), aggregation + alarm verdict (`metrics.py`) |
| `eval/` | behavioral arm: Inspect task (`aml_task.py`), under-escalation metrics + CIs (`metrics.py`) |
| `evaluator/` | interpretable verification: record schema, independent evaluator (`verify.py`), validation vs ground truth (`validate.py`) |
| `ledger/` | rendered decision ledger + distilled assurance summary |
| `finding/` | attestation finding (JSON + markdown) |
| `common/` | config, IO, LLM client, plotting + REPORT assembly |
| `config/config.yaml` | single source of truth (seeds, N, models, conditions, AML thresholds, typologies) |

## Data provenance (honest note)

The substrate is a **pure-Python port of AMLSim's typology-graph generator + a
faithful temporal emitter** (AMLSim's Java/MASON layer only does mechanical
timestamp stepping). Structuring/smurfing is realised as a `fan_in` of
sub-$10,000 cash deposits — AMLSim-native provenance for the target class.
Ground-truth labels come from **deterministic BSA/AML rules**, never an LLM, so
under-escalation is objectively measurable; the evaluator never sees them. Each
rule's statutory / supervisory basis (CTR/structuring statutes, FFIEC red flags,
FATF/OFAC jurisdiction lists) is documented in [`docs/RULE_BASIS.md`](docs/RULE_BASIS.md).

**Fidelity to AMLSim.** The port is checked against IBM AMLSim's *real* committed
Java/MASON sample output (vendored in `data/reference/amlsim_sample/`): account/
transaction schema, the cash vs. non-cash split, the transaction-type vocabulary,
the typology graph shapes (fan_in / fan_out / cycle / gather_scatter), and SAR
labeling all line up — see [`results/AMLSIM_FIDELITY.md`](results/AMLSIM_FIDELITY.md)
(`uv run python -m tools.amlsim_fidelity`, $0). Amounts/timing are deliberately
re-parameterized to BSA-realistic ranges, so they are not compared. Ingesting a real
AMLSim run directly (`dataset.substrate: csv`) is a planned seam, not yet implemented.

Models: agent `claude-sonnet-4-6`, independent evaluator `claude-opus-4-8`,
observability quality judge `claude-haiku-4-5`. See `config/config.yaml`.

## Security

See [`SECURITY.md`](SECURITY.md) — a reviewer's map: per-path network behavior, env vars,
what's written where, the explicit nevers, hash-pinned public dependencies, and how to
verify the battery hash and lockfile. The "air-gapped" and "we never see your key" claims
are enforced by tests (`tests/test_airgapped_selfcert.py`, `tests/test_no_secret_leak.py`).

**Verify it yourself.** `uv sync && ./scripts/verify.sh` runs the entire offline assay —
the data build, both end-to-end pipelines (stubbed), and every safety test — with no API
key and no cost, reproducing exactly what a fresh clone must pass. The same battery runs
in CI (`.github/workflows/ci.yml`) on every push.

## License

Licensed under the [Apache License 2.0](LICENSE). Copyright 2026 Superjective.

See [`LIMITATIONS.md`](LIMITATIONS.md) for the model/eval card — intended use,
out-of-scope boundaries, per-figure provenance, and the self-certification gap.

## Acknowledgements

The data substrate is a pure-Python port of [IBM AMLSim](https://github.com/IBM/AMLSim)
(Apache-2.0). If you build on the AMLSim dataset/generator, please cite Suzumura &
Kanezashi and the associated papers — full attribution, modifications, and BibTeX are
in [`NOTICE`](NOTICE).
