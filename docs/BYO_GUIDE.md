# Run Cupel on your own agent

> Cupel scores **your agent's decisions on the Cupel battery** —
> the only place ground truth exists. It cannot score arbitrary production logs, because
> your real alerts have no labels (that is the whole problem Cupel exists to sidestep).

There are two BYO paths. **LogReplay is the recommended one** (offline, lowest-trust).

---

## LogReplay — score a decisions CSV (zero network)

Three steps. Nothing about your data leaves your machine in steps 1–2; the
under-escalation number in step 3 is computed locally with **no network calls**
(enforced by `common.netguard`, proven in `tests/test_byo_logreplay.py`).

```bash
# 1. Export the battery (free, offline) — prompts only, no labels
uv run python -m data.build --export-battery        # -> results/byo/battery.jsonl

# 2. Run each prompt through YOUR agent, offline, and record a decisions CSV (see contract).

# 3. Score it — prints your under-escalation number, offline
uv run python run.py --agent logreplay --decisions your_decisions.csv
```

### CSV contract

| Column | Required | Meaning |
|---|---|---|
| `alert_id` | **yes** | Must match an `alert_id` from the exported battery. |
| `decision` | **yes** | `ESCALATE` or `CLEAR` (case-insensitive). |
| `condition` | no | `neutral` (default) or `incentivized`. See below. |
| `rationale` | recommended | Your agent's stated reason — what the independent evaluator inspects. |
| `reasoning` | no | Fuller chain-of-thought, if your agent exposes it. |

- **Extra columns are ignored.** Parsing is forgiving; every failure names the offending
  row and `alert_id`.
- **`(alert_id, condition)` must be unique.**
- **Conditions.** Provide **both** `neutral` and `incentivized` decisions (your agent run
  with and without its operating incentive) to get the full **susceptibility** report
  (REPORT + ledger + attestation). Provide a **single** condition for **independent
  verification** of those as-is decisions (ledger + validation).

A runnable example is committed at [`samples/sample_decisions.csv`](../samples/sample_decisions.csv).

### What touches the network

- **Your under-escalation number** (step 3, before any key): computed locally, **zero
  network**, nothing sent anywhere.
- **The independent ledger + attestation** (optional): runs only if `ANTHROPIC_API_KEY`
  is set, and sends the **decisions** (not raw data) to the evaluator — exactly as the
  reference run does. No other host is contacted; there is no telemetry.

---

## api (BETA) — point Cupel at your agent's endpoint

Treats your endpoint as a **black box**: Cupel POSTs one alert and reads back a decision.
It does **not** run its own prompt on your model. You expose a thin wrapper conforming to:

```
Request   POST <endpoint>   Content-Type: application/json
  { "alert_id": "<id>", "alert": "<battery prompt text>", "condition": "<label>" }

Response  application/json
  { "decision": "ESCALATE" | "CLEAR", "rationale": "<string>", "reasoning": "<optional>" }

Auth      if CUPEL_AGENT_API_KEY is set, sent as `Authorization: Bearer <key>`.
          No other host is contacted; no telemetry.
```

```bash
uv run python run.py --agent api --endpoint https://your-agent/triage --model "triage-v3"
```

This is an as-is verification (single condition). It is **beta**; if your endpoint isn't
ready, use LogReplay.

---

## Deliverables

A BYO run emits the same shapes as the reference run, namespaced under `byo_`:
`results/BYO_REPORT.md`, `results/ledger/byo_decision_ledger.md`,
`results/ledger/byo_assurance_summary.md`, `results/finding/byo_attestation.{json,md}`.
See [`LIMITATIONS.md`](../LIMITATIONS.md) for scope and the self-certification gap.
