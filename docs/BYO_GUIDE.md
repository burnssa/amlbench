# Run AMLBench on your own agent

> AMLBench scores **your agent's decisions on the AMLBench battery** —
> the only place ground truth exists. It cannot score arbitrary production logs, because
> your real alerts have no labels (that is the whole problem AMLBench exists to sidestep).

**Start with LogReplay.** You run our alerts through your agent yourself and score the
results locally, so nothing about your agent or your setup leaves your machine and you
need no API key to get your number. There is a second path (`api`) for teams who would
rather expose an endpoint than script a batch run; it is still beta and is described at
the end.

## Before you start

You need [uv](https://docs.astral.sh/uv/getting-started/installation/) and a clone of the
repo. No API key is needed to export the battery or to get your under-escalation number;
only the optional evaluator stage wants one (see Deliverables).

```bash
git clone https://github.com/burnssa/amlbench && cd amlbench
uv sync
```

If you want to satisfy yourself the harness does what this guide says before you run
anything through your own agent, `./scripts/verify.sh` runs the whole offline battery
(11 checks, no key, no cost). It covers the zero-network guarantee and the check that no
agent-visible string encodes a ground-truth label.

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

The export is **240 alerts**, one JSON object per line with `alert_id` and `prompt`. Alert
IDs are opaque (`A-0069`, `A-0198`), so nothing in the file tells your agent what the
answer is. It also writes `results/byo/battery_manifest.json`, which records that this is
the open practice tier: you hold the alerts, so a score computed on them is self-tested
and gameable by construction. The held-out challenge tier is server-side and never
exported (see [`docs/CHALLENGE_PROTOCOL.md`](CHALLENGE_PROTOCOL.md)).

Two optional flags on step 3: `--model "<label>"` names your agent in the report and
certificate, and `--out-root <dir>` writes deliverables somewhere other than `results/`
so a trial run doesn't overwrite a previous one.

### CSV contract

| Column | Required | Meaning |
|---|---|---|
| `alert_id` | **yes** | Must match an `alert_id` from the exported battery (the opaque `A-####` form). |
| `decision` | **yes** | `ESCALATE` or `CLEAR` (case-insensitive). |
| `condition` | no | `neutral` (default) or `incentivized`. See below. |
| `rationale` | recommended | Your agent's stated reason — what the independent evaluator inspects. |
| `reasoning` | no | Fuller chain-of-thought, if your agent exposes it. |

- **Extra columns are ignored.** Parsing is forgiving; every failure names the offending
  row and `alert_id`. Column headers are case-insensitive, surrounding whitespace is
  trimmed, and a CSV saved out of Excel or Sheets (UTF-8 with a byte-order mark, CRLF
  line endings) reads fine.
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

## Deliverables

A BYO run emits the same shapes as the reference run, namespaced under `byo_`:
`results/BYO_REPORT.md`, `results/ledger/byo_decision_ledger.md`,
`results/ledger/byo_assurance_summary.md`, `results/finding/byo_attestation.{json,md}`.
Alongside those you get `results/finding/byo_cert_request.json` (the aggregate-only
certificate request) and the raw run under `results/runs/byo/`: `decisions.jsonl`,
plus `verifications.jsonl` and `validation.json` once the evaluator stage has run.

The report, ledger, assurance summary and attestation need `ANTHROPIC_API_KEY`, since
they come from the independent evaluator. Without a key you still get your
under-escalation number and `decisions.jsonl`, and nothing leaves your machine.

See [`LIMITATIONS.md`](../LIMITATIONS.md) for scope and the self-certification gap.

---

## Alternative: point AMLBench at your endpoint (beta)

For teams who would rather expose an endpoint than script a batch run. It treats your
endpoint as a **black box**: AMLBench POSTs one alert and reads back a decision, and it
does **not** run its own prompt on your model. You expose a thin wrapper conforming to:

```
Request   POST <endpoint>   Content-Type: application/json
  { "alert_id": "A-0069", "alert": "<battery prompt text>", "condition": "<label>" }

Response  application/json
  { "decision": "ESCALATE" | "CLEAR", "rationale": "<string>", "reasoning": "<optional>" }

Auth      if AMLBENCH_AGENT_API_KEY is set, sent as `Authorization: Bearer <key>`.
          No other host is contacted; no telemetry.
```

```bash
uv run python run.py --agent api --endpoint https://your-agent/triage --model "triage-v3"
```

`alert_id` is the same opaque battery ID your agent sees in LogReplay, so you can log it
or pass it through your own context without handing your agent the answer.

### What beta means here

Three specific things, none of which apply to LogReplay:

1. **The request contract may change.** It is not yet frozen, so a wrapper you write today
   may need a small edit against a later version.
2. **One pass over the whole battery.** The run POSTs all **240 alerts**, 8 requests in
   flight at a time, with a 60-second timeout per request. Use `--workers <n>` to lower the
   concurrency if your endpoint is rate-limited. There is no way to run a short subset
   first, so point it at a test deployment before a production one.
3. **Failures score in your favour, so read the parse rate.** A request that errors or
   times out is recorded as ESCALATE with `parse_ok: false`, the same fail-safe our own
   harness uses. Those records are counted in the rates, so a badly failing endpoint looks
   like a very cautious agent. The run prints a warning with the parse rate whenever any
   decision could not be read, and the failures are in `results/runs/byo/decisions.jsonl`.
   Get to a clean 100% parse rate before you treat the number as a result.

This path runs a single condition, so it verifies your decisions as-is and gives you the
ledger and validation. The susceptibility comparison needs both a `neutral` and an
`incentivized` condition, which means LogReplay. If your endpoint is not ready, or you
want the full deliverable set, use LogReplay.
