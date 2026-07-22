# Probe experiment — where does the cover-story failure live?

> Design doc + working directory for the mech-interp follow-up to
> [AMLBENCH_FINDINGS.md](../docs/AMLBENCH_FINDINGS.md).
> Status: design.

## Layout

```
interp/
  README.md            # this spec
  build_probe_set.py   # generate the private probe alert set (fresh seeds, rule-labeled)
  presentation.py      # ledger-mode alert rendering (see "Presentation modes")
  capture/             # GPU-side activation capture (runs on RunPod, not locally)
  probes/              # probe training + analysis (runs anywhere from saved activations)
  runpod/              # pod bootstrap: image/deps, model download, tmux + Claude Code session
  data/                # PRIVATE — scaled holdout alerts + covers (gitignored; engagement asset)
  activations/         # bulk tensors synced from the pod (gitignored; regenerable)
  results/             # probe metrics, figures, tables — committed
```

The scaled probe-training set (~500 reportable + ~500 benign) and its covered variants live in
`data/` and are **never committed** — they double as private holdouts for client engagements.
The public, frozen canonical 60-alert sample remains the only published evaluation data.

## Presentation modes

The v0 harness shows most alerts a **pre-digested summary** (`agent/triage.py::present_alert`):
derived extract lines (grouped cash amounts, pre-paired pass-through, dispersion totals), a
structured-indicators block, and a profile-consistency verdict. That verdict line — "Activity
DEVIATES from the customer's expected profile" — correlates with the ground-truth label for
non-subtle classes, so a probe trained on the standard presentation could read a flag off the
input instead of measuring computed suspicion. Only `structuring_subtle` ships as a raw ledger.

**Ledger mode** (`presentation.py::present_alert_ledger`) therefore renders *every* alert the
subtle way: header facts + a sanctions-screening line + the full timestamped transaction ledger
with per-row counterparty account and country — no derived lines, no indicators block, no
profile verdict. Extraction *and* judgment are the model's job. The enriched rows (`ts`,
`counterparty`, `counterparty_country`, added in `data/build.py::extract_features`) keep every
deterministic rule decidable from the ledger alone: hour gaps for pass-through, distinct
beneficiaries for dispersion, per-row country for jurisdiction, the screening line for
watchlist. The screening line stays because it is a separate system's factual output, not a
judgment about the pattern. v0 prompt text is byte-identical under the enrichment (verified:
narratives and prompts unchanged on the seed-11 sample).

Capture runs under **both** modes: standard mode is the deployed condition the benchmark
numbers live in (and where the Replicate sanity gate applies); ledger mode is where the probe
claims are clean. Ledger-mode failure rates are **not comparable to the v0 leaderboard** —
weaker models' baselines will drop once extraction is on them, so ledger mode gets its own
baseline pass. Subtle alerts near-coincide across modes (rows gain timestamps/counterparties) —
a built-in consistency check.

The mode contrast is also an experiment in itself — **evidence density vs narrative capture**:
covers give the adversary anchor points, but a full ledger forces the cover to explain away
each transaction individually. If covers beat summaries but fail against ledgers, the deployer
guidance is "feed agents raw ledgers, not pre-digested summaries"; if covers still win, the
gullibility finding strengthens. Either outcome pays.

## Question

The data-adversary (Axis 3) bends every model, survives a spec-complete prompt, and — per the
findings — the model *recites* the "plausible innocent explanation does not defeat reasonable
suspicion" clause and fails to apply it. Behaviorally we cannot tell two stories apart:

1. **Deceived representation** — the cover corrupts the model's internal assessment of the
   evidence. The model genuinely no longer represents the alert as suspicious. A perception
   failure; steering the decision cannot fix it.
2. **Knows-but-clears** — the model still internally represents the pattern as suspicious, and the
   cover suppresses the *escalation decision* downstream. A judgment/decision failure; the kind of
   thing activation steering plausibly can fix, and mechanistically adjacent to
   sycophancy/deception phenomena.

A linear probe for "this alert is reportable," trained on raw (A0) activations and applied to
covered (A2) alerts, distinguishes them: if the probe stays high while the model clears →
knows-but-clears; if the probe follows the output down → deceived representation.

Run it separately on **Gemma-3-27B-IT** and **Llama-3-70B-Instruct** to test whether the failure
sits at a different *position* in the two models — in stage (representation vs decision) and in
depth (the layer profile where the reportable-vs-benign signal lives and where it dies under
cover).

## Why these two models

Their behavioral failure profiles (canonical run) are qualitatively different, not just scaled:

| | Gemma-3-27B | Llama-3-70B |
|---|---|---|
| false-escalation (benign) | **0.46** — indiscriminate over-flagging | 0.00 |
| JI directive, B0 → B2 | +0.94 → +0.06 — swings to whichever rule is stated | +0.46 → **+0.19** — residual under full spec |
| incentive | ~0 (immune) | +0.17 (susceptible) |
| A1 / A2 cover | **+0.09** / +0.50 | +0.50 / +0.67 |
| bright-line integrity under cover | 33% | **11%** |

**Pre-registered predictions** (falsifiable, written before capture):

- **Llama = deceived representation.** Worst-in-panel integrity (11% — covers talk it out of
  *overt structuring*) and a large A1 jump suggest the narrative corrupts the evidence
  representation itself. Prediction: probe AUROC on covered alerts degrades substantially; the
  probe follows the output; the layer profile shows the suspicious-signal weakening at the layers
  where it first forms.
- **Gemma = decision-stage failure on a weakly-separated representation.** The FP profile (46%
  benign escalated) predicts the raw reportable-vs-benign separation is *weak* at every layer —
  over-flagging as poor discrimination, visible in probe geometry, not just behavior. The
  directive swing (+0.94 with rule inversion, ~0 incentive) suggests instruction-text dominates
  the decision late. Prediction: A1 barely moves the representation (matching A1 Δ +0.09); the A2
  KYC context and directives move the *decision* while the (weak) evidence signal persists —
  knows-but-clears, or more precisely "never-strongly-knew, decides-by-instruction."

If the double dissociation holds — cover attacks hit representation (early), directive attacks hit
decision (late, representation intact) — that upgrades the findings-doc dichotomy (*directive
patchable by spec, data-cover not*) from a behavioral observation to a mechanistic account: **spec
language can re-anchor a decision rule but cannot repair a corrupted evidence representation.**

## Design

### Data (mostly free — the pipeline is deterministic)

- **Probe train/val:** regenerate alerts via `data/build.py` across fresh seeds until ~500
  reportable + ~500 benign. Labels are deterministic (`data/rules.py`), narratives templated (no
  LLM) — free and fully reproducible. **Hold out the canonical 60-alert sample entirely.**
- **Covered eval set:** ~100–150 held-out reportable alerts run through `eval/adversary_gen.py`
  (Opus-authored A1 + A2, overt-structuring control retained as the ecological-validity gate).
  Cost order-of-magnitude: canonical run was ~$34 all-in; a covers-only pass over 150 alerts is
  comparable or less.
- **Controls (both needed to make the probe result mean anything):**
  - **Neutral elaboration:** covered-style narrative of matched length/register that is *not*
    exculpatory (routine detail, no innocent rationale). Separates "more narrative text shifts the
    representation" from "the exculpatory story shifts it."
  - **Benign + innocuous cover:** benign alerts with the same narrative treatment. Checks the
    probe's false-positive behavior under narrative load and later prices any steering
    intervention's specificity cost.
- **Template-leak check:** narratives are templated per typology, so a probe could key on surface
  template features rather than the evidence pattern. Two guards: (a) verify benign and reportable
  windows render through overlapping templates; (b) leave-one-typology-out probe evaluation — a
  probe that transfers across typologies is reading "suspicious pattern," not "template ID."

### Activation capture

Replicate (the harness path for both models) never exposes hidden states — this leg needs its own
GPU path, `transformers` + `output_hidden_states` (or nnsight hooks), chat-template-faithful to the
harness prompts.

- **Condition = the Axis-3 condition exactly:** spec-complete base (B2), accurate-triage
  instruction, no incentive, no directive. Plus one directive condition (JI at B0) for the
  dissociation test. Each condition is captured under **both presentation modes** (see
  "Presentation modes"): probe training and the core claims run on ledger mode; standard mode
  anchors comparability to the benchmark numbers.
- **Models/fit:** Gemma-3-27B-IT bf16 ≈ 55 GB → one 80 GB card (A100/H100). Llama-3-70B-Instruct
  bf16 ≈ 140 GB → 2×H100, or int8 on one 80 GB card (quantized activations are generally fine for
  probing; validate by checking the probe replicates at a sampled layer in bf16 before trusting
  cross-condition comparisons).
- **Positions saved:** all layers at (i) last token of the alert data, (ii) last prompt token
  (pre-decision), (iii) the decision token(s). Plus a per-token probe pass over the narrative span
  for the token-position analysis. ~1.5k prompts × 2–3 conditions × 2 models is a few GPU-hours —
  rental cost is noise compared to the API spend already in the project.
- **Sanity gate before any probing:** the local checkpoints must reproduce the Replicate failure
  profile on the canonical 60 (sensitivity, false-esc, A2 Δ, integrity, within sampling noise).
  If the local Llama-3-70B differs from Replicate's serving stack, that's a finding to resolve
  first, not to average over.

### Probes and analyses

1. **Layer sweep (the "depth position").** Per layer: mass-mean difference direction +
   logistic-regression probe, reportable vs benign, trained on raw A0 at the last-alert-token
   position. Report AUROC-by-layer per model. Gemma prediction: low ceiling everywhere (weak
   separation ↔ 46% FP). Llama prediction: clean high-AUROC band.
2. **The core 2×2 (the "stage position").** Apply the best-layer probe to A2 covered alerts. Per
   alert: probe score × model decision. The quantity of interest is
   **P(probe-suspicious | model clears)** — the knows-but-clears rate — per model, with the
   neutral-elaboration control subtracted.
3. **Token-position trajectory.** Probe score across the narrative: does it drop *locally at the
   cover-story sentences* (evidence reweighting as the story is read) or stay high through the
   data and collapse only near the decision (late suppression)?
4. **Directive dissociation.** Same probes under the JI directive at B0 (both models swing there).
   Prediction: representation intact, decision moved — opposite quadrant from the cover condition.
5. **Steering (conditional — run only if knows-but-clears is substantial).** Use the probe/CAA
   direction at the implicated layer; add during decision on covered alerts. Report sensitivity
   recovered **and** specificity cost on the benign+cover control in the same table. Gemma is the
   stress test: if FN and FP sit on one poorly-separated direction, steering trades one for the
   other — "you can steer Gemma paranoid, not competent" is a publishable negative result.
6. **SAE leg (Gemma only; GemmaScope 2 covers Gemma-3-27B-IT).** Decompose the probe direction and
   the cover-induced activation delta into SAE features: is the cover recruiting identifiable
   deference/"user-asserted-fact" features, and do the same features light up under the JI
   directive? This is the "gullibility as a general, reusable mechanism" bridge — if the same
   features mediate both, cover-susceptibility is not AML-specific.

## Interpretation tree

| probe on A2 | model decision | reading |
|---|---|---|
| stays suspicious | clears | knows-but-clears — decision-stage failure; steerable; sycophancy-adjacent |
| follows output down | clears | deceived representation — perception failure; explains why spec language can't patch it |
| weakly separated even at A0 | over-escalates benign | (Gemma FP story) no discrimination to protect — the failure precedes any adversary |
| intact under JI directive, moved under cover | — | double dissociation → mechanistic version of the two-attack-surface thesis |

Mixed outcomes are informative, not failures: a split by typology (bright-line vs judgment-call
alerts landing in different quadrants) would itself explain why integrity and A2 must be read
together.

## Caveats to carry into the write-up

- Linear probes lower-bound what the model represents; "probe follows output" is evidence of
  representation corruption, not proof (nonlinear signal may persist).
- Covers remain Opus-authored — the adversary is fixed across target models, which is what makes
  the cross-model comparison clean, but inherits the survivorship caveats of the cover library.
- Local-vs-Replicate serving differences must be resolved by the sanity gate before any
  activation claim.
- n ≈ 150 covered alerts puts ±~4–8 pts on the quadrant rates — report intervals, read for shape.
