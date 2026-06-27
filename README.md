# Cupel — behavioral assurance + interpretable verification for a financial AI agent

> A Superjective project. Cupel independently audits a financial-crime triage agent for
> behavioral failures that standard LLM observability cannot see.

A rigorous, quantified worked example proving two pillars of independent assurance
for an AML transaction-monitoring agent under a **sabotage-style evaluation** (a
legitimate triage task plus a hidden incentive to clear alerts to hit a
throughput / false-positive-reduction metric):

- **Pillar A — detection.** A fairly-configured observability/quality stack
  (Arize Phoenix: tracing + groundedness/coherence/hallucination evals + drift)
  **does not surface** the failure, while an independent **behavioral assessment
  quantifies** the under-escalation against ground truth.
- **Pillar B — interpretable verification.** An independent evaluator (Claude
  Opus 4.8) emits a **human-interpretable verification record for every decision**
  — what the alert contained, the criteria in play, whether the decision is
  *defensible* and the rationale *faithful*, and an examiner-readable note — and is
  **validated against ground truth**.

## Quickstart

The data layer is free and offline; everything that calls a model needs your own
`ANTHROPIC_API_KEY` (and costs a few dollars). Cost is stated above each command.

```bash
uv sync                                   # install deps
uv run python -m data.build               # generate the labeled dataset — offline, FREE, no key
```

**Run it on our reference agent:**

```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env # BYO key; the commands below spend a few $

uv run python run.py --mode dry           # ~24 alerts, plumbing check (~$1-2)
uv run python run.py --mode core          # full N=240, 1 seed / 1 phrasing (the headline run)
uv run python run.py --mode full          # all seeds x all phrasings (robustness)
```

**Run it on YOUR agent** (BYO — see [`docs/BYO_GUIDE.md`](docs/BYO_GUIDE.md)). LogReplay
is offline and prints your under-escalation number with **zero network calls**; the
optional ledger/attestation stage needs the key:

```bash
uv run python -m data.build --export-battery               # prompts only, no labels — FREE
# run those prompts through your agent → a decisions CSV (see the CSV contract), then:
uv run python run.py --agent logreplay --decisions your_decisions.csv
```

Outputs land in:

- `results/REPORT.md` — thesis, method, **domain primer** (embedded from `docs/DOMAIN_BACKGROUND.md`), quantified results, plots, sample records, limitations
- `docs/DOMAIN_BACKGROUND.md` — AML/BSA primer: KYC vs transaction monitoring vs triage, the typology shapes, and how the synthetic data maps to real alerts
- `results/ledger/decision_ledger.md` — full per-decision verification ledger
- `results/ledger/assurance_summary.md` — distilled examiner-facing package
- `results/finding/attestation.{json,md}` — the attestation finding
- `results/runs/<mode>/*.{json,jsonl}` — raw decisions, quality scores, verifications, metrics
- `results/plots/*.png`

The standalone Inspect AI behavioral task (a second, independent implementation of
the behavioral arm) can be run on its own:

```bash
uv run inspect eval eval/aml_task.py --model anthropic/claude-sonnet-4-6 -T condition=incentivized -T phrasing=throughput_backlog
uv run inspect eval eval/aml_task.py --model anthropic/claude-sonnet-4-6 -T condition=neutral
```

## Layout

| dir | what |
|---|---|
| `data/` | AMLSim-derived substrate (`amlsim.py`), alert builder (`build.py`), deterministic BSA/AML ground-truth labeler (`rules.py`) |
| `agent/` | triage agent (`triage.py`) + matched neutral/incentivized conditions (`conditions.py`) |
| `observability/` | Pillar A obs arm: Phoenix tracing + quality evals (`instrument.py`), aggregation + alarm verdict (`metrics.py`) |
| `eval/` | Pillar A behavioral arm: Inspect task (`aml_task.py`), under-escalation metrics + CIs (`metrics.py`) |
| `evaluator/` | Pillar B: record schema, independent evaluator (`verify.py`), validation vs ground truth (`validate.py`) |
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
under-escalation is objectively measurable; the evaluator never sees them. To use
a real AMLSim Java run instead, set `dataset.substrate: csv` and `dataset.csv_dir`.

Models: agent `claude-sonnet-4-6`, independent evaluator `claude-opus-4-8`,
observability quality judge `claude-haiku-4-5`. See `config/config.yaml`.

## Security

See [`SECURITY.md`](SECURITY.md) — a reviewer's map: per-path network behavior, env vars,
what's written where, the explicit nevers, hash-pinned public dependencies, and how to
verify the battery hash and lockfile. The "air-gapped" and "we never see your key" claims
are enforced by tests (`tests/test_airgapped_selfcert.py`, `tests/test_no_secret_leak.py`).

## License

Licensed under the [Apache License 2.0](LICENSE). Copyright 2026 Superjective.

See [`LIMITATIONS.md`](LIMITATIONS.md) for the model/eval card — intended use,
out-of-scope boundaries, per-figure provenance, and the self-certification gap.

---
_A Superjective project._
