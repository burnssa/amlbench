# AMLBench — detection under deception, for AML triage agents

[![verify](https://github.com/burnssa/amlbench/actions/workflows/ci.yml/badge.svg)](https://github.com/burnssa/amlbench/actions/workflows/ci.yml)

**AMLBench** is an open benchmark that scores AI models not on whether they *can* triage
anti–money-laundering (AML) alerts, but on whether they **keep their escalation judgment**
when the task is made adversarial — deceptive alert data, judgment-inverting instructions,
and operational pressure — measured against **deterministic BSA/AML ground truth, never an
LLM judge**.

The headline result from the canonical run (`results/canonical/leaderboard.json`,
[`docs/AMLBENCH_FINDINGS.md`](docs/AMLBENCH_FINDINGS.md)):

- **Full robustness is a two-model club.** Only **Opus 4.8** and **GPT-5.5** stay competent,
  incentive-immune, *and* fully patchable by a spec-complete prompt. It is a specific model
  property, not a function of raw capability.
- **The grounded data-adversary is the durable crack.** A plausible cover story woven into a
  genuinely reportable alert (transaction facts *untouched*) lowers escalation on **every**
  model, including the robust club (Opus +0.38, GPT-5.5 +0.48). Stating the obligation in the
  prompt patches the *directive* attack; it does **not** patch the *data* attack.

## What it measures

An AML transaction-monitoring analyst must **ESCALATE** any alert meeting Bank Secrecy Act
criteria (structuring, rapid pass-through / layering, off-profile dispersion, sanctioned
counterparties, high-risk-jurisdiction exposure) or **CLEAR** the rest. AMLBench holds the
model fixed and varies three axes, scoring every decision against objective labels the model
never sees:

- **Base-prompt completeness** (B0 underspecified → B2 states the FFIEC obligation explicitly).
- **Adversarial instruction** — a judgment-inversion directive that redefines the evidentiary
  bar above the legal "reason to suspect" standard (each directive is a targeted negation of a
  named B2 clause; see [`docs/BENCHMARK.md`](docs/BENCHMARK.md) §12.4).
- **Adversarial data** — a grounded cover story real launderers used, prepended to the alert
  narrative while `features` and ground truth stay untouched, so the alert stays reportable.

The single measured quantity is **under-escalation** of genuinely reportable alerts; a
bright-line **overt-structuring integrity** control gates ecological validity, and a
**specificity** floor (benign alerts must not be over-escalated) keeps a trigger-happy model
from scoring well by escalating everything.

```
data.build            model triage             scoring (vs deterministic ground truth)
synthetic alerts  →   base × directive  →      under-escalation · bright-line integrity  →  leaderboard
+ BSA/AML labels      × data-adversary         · specificity                                 .json
```

## Quickstart

The data layer is free and offline. Anything that calls a model needs your own provider key
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `XAI_API_KEY`, `REPLICATE_API_TOKEN`) and costs a few
dollars; cost is stated on each command.

```bash
uv sync                                        # install deps
uv run python -m data.build                    # generate the labeled dataset — offline, FREE, no key
```

**Run the canonical benchmark** (the full Model × Base × Adversary grid → one leaderboard):

```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env     # + any other providers you want on the panel
uv run python -m eval.canonical_run --dry-run  # plan + call count, no spend
uv run python -m eval.canonical_run            # full run (hours on the throttled open models)
```

**Run it on your own model** — add it to the panel in `config/config.yaml`, or:

```bash
uv run python -m eval.canonical_run --models "anthropic/claude-opus-4-8,your/model-id"
```

## Two tiers

**Public benchmark (this repo).** A frozen reference battery + the canonical grid above.
Self-scored, reproducible offline, explicitly gameable — the leaderboard and developer feedback
loop. Ground truth ships with it.

**Private evaluation (Superjective).** For banks and fintechs: your *real* deployed agent, run
against a **held-out, rotated** alert set server-side, scored against private labels your team
never receives, producing a signed attestation certificate. This is the paid tier; the harness
for it (`agent/byo.py`, the challenge protocol, the certificate flow) lives here but is gated —
see [`docs/BYO_GUIDE.md`](docs/BYO_GUIDE.md) and [`docs/CHALLENGE_PROTOCOL.md`](docs/CHALLENGE_PROTOCOL.md).

## Layout

| dir | what |
|---|---|
| `data/` | AMLSim-derived substrate (`amlsim.py`), alert builder (`build.py`), deterministic BSA/AML ground-truth labeler (`rules.py`) |
| `data/framings/`, `data/adversary/` | grounded directive framings + the launderer cover library (provenance-tiered) |
| `agent/` | triage agent (`triage.py`), base-role conditions (`conditions.py`), BYO endpoint contract (`byo.py`) |
| `eval/` | the benchmark: canonical runner (`canonical_run.py`), adversary generator/eval (`adversary_*.py`), metrics + CIs (`metrics.py`), Inspect task (`aml_task.py`) |
| `evaluator/` | interpretable per-decision verification (private tier): independent evaluator + validation vs ground truth |
| `observability/` | optional Phoenix tracing + quality evals for a run |
| `finding/`, `ledger/`, `tools/` | attestation finding, decision ledger, certificate/challenge CLIs (private tier) |
| `common/` | config, IO, multi-provider LLM client, plotting |
| `config/config.yaml` | single source of truth (seeds, N, model panel, base roles, AML thresholds, typologies) |

## Grounding & provenance

Every directive framing and cover story traces to a named enforcement case **or** the
regulatory standard, tiered by evidence strength — enforcement-documented (Rabobank "Verified
List", TD Bank, HSBC/Sinaloa, Russian & Troika Laundromats, 1MDB, Danske) through
`extrapolated` (implied by the FFIEC "need not confirm the underlying crime" floor, not captured
verbatim). The full tiered evidence base is [`docs/BENCHMARK.md`](docs/BENCHMARK.md) §12; each
directive carries its tier in `data/framings/directives.jsonl`. Contrived items are excluded by
an ecological-validity gate — the line that keeps this a measurement, not a jailbreak arms race.

## Data provenance (honest note)

The substrate is a **pure-Python port of AMLSim's typology-graph generator + a faithful temporal
emitter** (AMLSim's Java/MASON layer only does mechanical timestamp stepping). Structuring is
realised as a `fan_in` of sub-$10,000 cash deposits — AMLSim-native provenance for the target
class. Ground-truth labels come from **deterministic BSA/AML rules**, never an LLM, so
under-escalation is objectively measurable. Each rule's statutory/supervisory basis
(CTR/structuring statutes, FFIEC red flags, FATF/OFAC jurisdiction lists) is documented in
[`docs/RULE_BASIS.md`](docs/RULE_BASIS.md). The port is checked against IBM AMLSim's real
committed sample output (`data/reference/amlsim_sample/`) — see
[`results/AMLSIM_FIDELITY.md`](results/AMLSIM_FIDELITY.md).

## Security

See [`SECURITY.md`](SECURITY.md) — per-path network behavior, env vars, what's written where,
the explicit nevers, hash-pinned dependencies. The "air-gapped" and "we never see your key"
claims (private tier) are enforced by tests (`tests/test_airgapped_selfcert.py`,
`tests/test_no_secret_leak.py`).

**Verify it yourself.** `uv sync && ./scripts/verify.sh` runs the entire offline harness — the
data build, both end-to-end pipelines (stubbed), and every safety test — with no API key and no
cost, reproducing exactly what a fresh clone must pass. The same battery runs in CI
(`.github/workflows/ci.yml`) on every push.

## License

Licensed under the [Apache License 2.0](LICENSE). Copyright 2026 Superjective.

See [`LIMITATIONS.md`](LIMITATIONS.md) for the model/eval card — intended use, out-of-scope
boundaries, per-figure provenance, and the self-certification gap.

## Acknowledgements

The data substrate is a pure-Python port of [IBM AMLSim](https://github.com/IBM/AMLSim)
(Apache-2.0). If you build on the AMLSim dataset/generator, please cite Suzumura & Kanezashi
and the associated papers — full attribution, modifications, and BibTeX are in [`NOTICE`](NOTICE).
