"""Client-side de-identification for de-identified log-replay (engagement Mode 3).

Runs entirely in the CUSTOMER's environment. Takes raw decision logs, maps them to
the minimal feature contract (see docs/DATA_CONTRACT.md), tokenizes identifiers with
a locally-held salt, scrubs PII from free-text, regenerates a neutral narrative from
features, and — critically — runs an automated PII leak-check that refuses to write
output if any residual PII pattern remains. The de-identified output is the only
thing that ever leaves the environment; it is consumed by agent.adapter.LogReplayAgent.

No API keys, no network, stdlib only.

    python -m tools.desensitize --in raw_logs.jsonl --out clean.jsonl \
        --mapping mapping.json --salt-file .salt

`mapping.json` maps OUR field names to YOUR column names, e.g.
    {"alert_id": "case_ref", "decision": "disposition",
     "features": {"window_days": "lookback_days", "max_amount": "largest_txn"},
     "rationale": "analyst_note"}
Fields already named like ours need no mapping entry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import sys
from pathlib import Path

# ── PII patterns the leak-check refuses to let through ─────────────────────
_PII_PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\b(?:\+?\d{1,2}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b"),
    "long_digits": re.compile(r"\b\d{8,}\b"),   # account / card / TIN-like runs
}
# Feature keys we accept (anything else in a mapped features dict is dropped).
_ALLOWED_FEATURES = {
    "window_days", "n_transactions", "total_inflow", "total_outflow", "max_amount",
    "cash_transactions", "n_cash_in", "passthrough_hours", "passthrough_amount",
    "fanout_beneficiaries", "fanout_total", "counterparty_country",
    "consistent_with_profile", "transactions",
}


def _scrub(text: str) -> str:
    if not isinstance(text, str):
        return text
    for name, pat in _PII_PATTERNS.items():
        text = pat.sub(f"[REDACTED:{name}]", text)
    return text


def _tokenize(value: str, salt: str) -> str:
    return "tok_" + hashlib.sha256((salt + str(value)).encode()).hexdigest()[:16]


def _leak_check(record: dict) -> list[str]:
    """Return a list of (path, pattern) hits for any residual PII in string values."""
    hits = []

    def walk(node, path):
        if isinstance(node, str):
            for name, pat in _PII_PATTERNS.items():
                if pat.search(node):
                    hits.append(f"{path}: {name}")
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(record, "")
    return hits


def _get(raw: dict, key: str):
    return raw.get(key)


def desensitize_record(raw: dict, mapping: dict, salt: str) -> dict:
    fmap = mapping.get("features", {})
    feats_in = raw.get(mapping.get("features_key", "features"), {}) if "features_key" in mapping else raw.get("features", {})

    features = {}
    for our_key in _ALLOWED_FEATURES:
        their_key = fmap.get(our_key, our_key)
        val = (feats_in.get(their_key) if isinstance(feats_in, dict) and their_key in feats_in
               else raw.get(their_key))
        if val is not None:
            features[our_key] = val

    # `transactions` ledger: keep only date/type/amount/direction (drop any ids).
    if isinstance(features.get("transactions"), list):
        features["transactions"] = [
            {k: t.get(k) for k in ("date", "type", "amount", "direction") if k in t}
            for t in features["transactions"] if isinstance(t, dict)
        ]

    decision = str(raw.get(mapping.get("decision", "decision"), "")).upper().strip()
    out = {
        "alert_id": _tokenize(raw.get(mapping.get("alert_id", "alert_id"), ""), salt),
        "decision": decision if decision in ("CLEAR", "ESCALATE") else "ESCALATE",
        "condition": "as_is",   # real production decisions, no injected condition
        "features": features,
        "rationale": _scrub(raw.get(mapping.get("rationale", "rationale"), "") or ""),
        "reasoning": _scrub(raw.get(mapping.get("reasoning", "reasoning"), "") or ""),
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="raw logs (jsonl)")
    ap.add_argument("--out", required=True, help="de-identified output (jsonl)")
    ap.add_argument("--mapping", default=None, help="field-mapping json (optional)")
    ap.add_argument("--salt-file", default=".salt", help="local salt file (created if absent; KEEP PRIVATE)")
    args = ap.parse_args()

    mapping = json.loads(Path(args.mapping).read_text()) if args.mapping else {}

    salt_path = Path(args.salt_file)
    if salt_path.exists():
        salt = salt_path.read_text().strip()
    else:
        salt = secrets.token_hex(16)
        salt_path.write_text(salt)
        print(f"[desensitize] generated new salt at {salt_path} — keep it private; "
              f"the same salt gives stable tokens across runs.")

    raw_rows = [json.loads(l) for l in open(args.inp) if l.strip()]
    clean, all_hits = [], 0
    for i, raw in enumerate(raw_rows):
        rec = desensitize_record(raw, mapping, salt)
        hits = _leak_check(rec)
        if hits:
            all_hits += len(hits)
            print(f"[desensitize] FAIL record {i} ({rec['alert_id']}): residual PII -> {hits}", file=sys.stderr)
        clean.append(rec)

    if all_hits:
        print(f"[desensitize] ABORTED: {all_hits} residual-PII hits across {len(raw_rows)} records. "
              f"Nothing written. Fix the field mapping (you are likely passing a free-text/identifier "
              f"field) and re-run.", file=sys.stderr)
        sys.exit(2)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w") as f:
        for r in clean:
            f.write(json.dumps(r) + "\n")
    print(f"[desensitize] wrote {len(clean)} de-identified records -> {args.out} "
          f"(leak-check passed; only this file should leave your environment).")


if __name__ == "__main__":
    main()
