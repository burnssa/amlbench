# Security & supply chain

> This page is a **reviewer's map**: enough for a model-risk or
> security team to sign off without reading every file. It backs the six safety claims on
> the landing page, and the two load-bearing ones are enforced by tests, not prose.

## What touches the network, per path

| Path | Network |
|---|---|
| `data.build` (incl. `--export-battery`) | **Nothing.** Offline, deterministic. |
| `--agent logreplay` → your under-escalation number | **Nothing.** Enforced by `common.netguard` and proven end-to-end by `tests/test_airgapped_selfcert.py`. |
| `--agent api` | **Only the `--endpoint` you provide.** No other host. |
| Optional verification stage (Pillar B evaluator + Phoenix quality judge) | **Only the model provider** (e.g. `api.anthropic.com`) using *your* key. This stage sends decisions — never raw data — and runs only when a key is set. |
| Reference / cross-provider agent runs (`run.py --mode …`, `--model gpt-4o …`) | The named provider's API only. |
| Arize Phoenix tracing | **Local only** (localhost UI); traces stay on your machine. |

The "air-gapped" claim means exactly this: the entire self-cert path
(`data.build → export → logreplay → cert_request`) completes with **all outbound TCP
blocked** — `tests/test_airgapped_selfcert.py` runs it under `netguard.no_network()`.

## Secrets

- **Read from environment only**, never from arguments or written to any artifact.
- The "you supply your own key; AMLBench never sees it" claim is enforced by
  `tests/test_no_secret_leak.py`: no key-shaped value appears in any emitted artifact
  (report, ledger, attestation, `cert_request.json`).
- Env vars read:

  | Var | Used for |
  |---|---|
  | `ANTHROPIC_API_KEY` | agent + independent evaluator + Phoenix quality judge |
  | `OPENAI_API_KEY` | cross-provider agent (`gpt-4o`) |
  | `REPLICATE_API_TOKEN` / `REPLICATE_API_KEY` | open-weight agent (Replicate) |
  | `TOGETHER_API_KEY` / `FIREWORKS_API_KEY` / `OPENROUTER_API_KEY` / `GROQ_API_KEY` | optional OpenAI-compatible hosts |
  | `AMLBENCH_AGENT_API_KEY` | optional Bearer auth to **your** `--agent api` endpoint |
  | `REPLICATE_MIN_INTERVAL` | rate-limit tuning (not a secret) |

  Keys live in a `.env` at the repo root (gitignored) or the real environment.

## What is written, where

`data/alerts.jsonl` (battery) · `results/runs/<mode>/*.{json,jsonl}` · `results/REPORT.md` ·
`results/ledger/*.md` · `results/finding/*.{json,md}` (incl. `cert_request.json`) ·
`results/plots/*.png` · `results/certs/*.json` (signed certs) · `.phoenix/` (local traces,
gitignored). BYO outputs (`results/byo/`, `results/runs/byo/`, `results/{BYO_REPORT.md,
ledger/byo_*,finding/byo_*}`) are customer-specific and **gitignored**.

## Explicit nevers

- **No telemetry or analytics** from AMLBench's own code.
- **No auto-update**, no phone-home, no background network.
- **No install / postinstall / build hooks** — the build backend is `hatchling` with no
  custom scripts; installing the package runs no code of ours.
- **No `curl | bash`**, no remote bootstrap, anywhere.

## Supply chain — pinned, public, verifiable

- **Hash-pinned:** `uv.lock` pins every transitive dependency to an exact version **and
  sha256 hash**.
- **Public indices only:** every source is the public PyPI index
  (`https://pypi.org/simple`). **No git, url, or path dependencies.**
- **Verify what you pulled:**

  ```bash
  uv lock --check          # lockfile matches pyproject (no drift)
  uv sync --locked         # install EXACTLY the locked, hash-verified versions
  # battery integrity — compare to the published hash:
  uv run python -c "from tools.certify import _battery_hash; print(_battery_hash())"
  # expected: sha256:604eb3a04b6ef722
  ```

- **Certificates** are Ed25519-signed (`tools/certify.py`); verify any cert against the
  committed public key with `uv run python -m tools.certify verify --cert <file>`.

## Reproduce the safety tests

```bash
uv run python tests/test_airgapped_selfcert.py   # self-cert path completes with network blocked
uv run python tests/test_no_secret_leak.py       # no key value in any emitted artifact
uv run python tests/test_byo_logreplay.py        # logreplay ingest is zero-network
uv run python tests/test_cert_request.py         # cert_request is aggregate-only
```

## Disclosure

Report vulnerabilities privately to **security@superjective.ai** (or open a private
GitHub Security Advisory on the repository). Please do not file public issues for
security reports. We aim to acknowledge within 3 business days.
