#!/usr/bin/env bash
# AMLBench offline verification battery.
#
# Everything a fresh clone must pass with NO API key and no cost. This is what a
# cautious prospect (or a reviewer) can run to convince themselves the assay works,
# and it is exactly what CI runs on every push. If any step here needs a network
# call or a model key, that is a bug — the offline/air-gapped claims depend on it.
#
#   uv sync && ./scripts/verify.sh
#
set -uo pipefail
cd "$(dirname "$0")/.."

# Simulate a cautious prospect: no model keys in the environment. (offline_smoke and
# byo_smoke set their own stub key internally; nothing here reaches a real provider.)
unset ANTHROPIC_API_KEY OPENAI_API_KEY REPLICATE_API_TOKEN 2>/dev/null || true

fail=0
step() {
  local name="$1"; shift
  printf '  %-46s' "$name"
  if "$@" >/tmp/amlbench_verify.log 2>&1; then
    echo "PASS"
  else
    echo "FAIL"
    sed 's/^/        /' /tmp/amlbench_verify.log | tail -15
    fail=1
  fi
}

echo "== AMLBench offline verification (no API key, zero network beyond deps) =="

# Data layer (free, offline) — the foundation of every run.
step "data.build (labeled dataset)"            uv run python -m data.build
step "data.build --export-battery"             uv run python -m data.build --export-battery

# Full pipelines end-to-end, stubbed (no network / no cost).
step "offline_smoke (reference pipeline)"      uv run python tests/offline_smoke.py
step "byo_smoke (BYO deliverables)"            uv run python tests/byo_smoke.py

# The enforced safety guarantees (documented in SECURITY.md).
step "airgapped self-cert (network blocked)"   uv run python tests/test_airgapped_selfcert.py
step "no secret leak in artifacts"             uv run python tests/test_no_secret_leak.py
step "BYO logreplay is zero-network"           uv run python tests/test_byo_logreplay.py
step "cert_request is aggregate-only"          uv run python tests/test_cert_request.py
step "independent attestation tier is gated"   uv run python tests/test_certify_gate.py

# Headline reproduction from committed fixtures (the agent-facing repro; self-checks itself).
step "repro headline (reproduced from logs)"   uv run python -m tools.repro

echo
if [ "$fail" -eq 0 ]; then
  echo "ALL PASS ✓  — a fresh clone runs the offline assay with no key."
else
  echo "FAILURES ✗  — see output above."
fi
exit "$fail"
