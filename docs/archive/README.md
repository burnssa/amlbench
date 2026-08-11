# Archive

Superseded design docs, kept because the path the project took is part of the evidence.
AMLBench set out to measure whether hidden operational pressure corrupts an AML triage
agent, and the ablation falsified that on the frontier. These documents are what the plan
looked like before the evidence moved it.

Nothing here is current. For live documentation start at [`../../README.md`](../../README.md),
and for results use [`../AMLBENCH_FINDINGS.md`](../AMLBENCH_FINDINGS.md) plus
`results/canonical_v0.2/leaderboard.json`.

| Doc | What it was | Why it is here |
|---|---|---|
| [`BENCHMARK_PLAN.md`](BENCHMARK_PLAN.md) | The item-generation flywheel: a fitness function for searching incentive framings, plus the framing-record schema and a phased build plan. | Built around the incentive axis, which the canonical run showed is largely inert on the frontier. The methodology still reads well; the framing it serves does not. |
| [`CANONICAL_RUN.md`](CANONICAL_RUN.md) | The pre-run design for the first complete Model × Base × Adversary run, written for sign-off before spending on it. | The run has since happened twice (v0, then the leak-corrected v0.2). The doc still describes it as pending and points at the superseded `results/canonical/` path. |
