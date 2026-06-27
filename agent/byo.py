"""Bring-your-own-agent ingest: score a CUSTOMER's agent on the Cupel battery.

Cupel can only compute an under-escalation rate where it has ground truth, and that
ground truth exists only on its synthetic battery — not on a customer's real alerts.
So the BYO workflow is keyed to the battery, not to arbitrary production logs:

    1. Export the battery:   uv run python -m data.build --export-battery
       -> results/byo/battery.jsonl  ({alert_id, prompt} — NO labels)
    2. The customer runs each prompt through THEIR OWN agent, offline.
    3. They return a decisions CSV (see CSV CONTRACT below).
    4. Score it:             uv run python run.py --agent logreplay --decisions <csv>

Two ingest paths:
  * logreplay (the hero) — read a decisions CSV. Pure file I/O; makes ZERO network
    calls (enforced by common.netguard in run.py + tests/test_byo_logreplay.py).
  * api (BETA) — treat a customer endpoint as a black box: POST one alert, read back
    {decision, rationale}. Calls ONLY that endpoint. The customer writes a thin wrapper
    conforming to the contract below; Cupel does NOT run its own prompt on their model
    (that would test the stand-in, not their agent).

──────────────────────────────────────────────────────────────────────────────
CSV CONTRACT (logreplay)
  Required columns:  alert_id, decision
  Optional columns:  condition (default "neutral"), rationale, reasoning
  - decision is case-insensitive ESCALATE / CLEAR.
  - extra columns are ignored.
  - alert_id must exist in the exported battery.
  - (alert_id, condition) must be unique.
  A susceptibility comparison needs both a `neutral` and an `incentivized` condition;
  a single condition yields independent verification of those as-is decisions.

API CONTRACT (api, BETA)
  Request  (POST <endpoint>, application/json):
      {"alert_id": "<id>", "alert": "<the battery prompt text>", "condition": "<label>"}
  Response (application/json):
      {"decision": "ESCALATE"|"CLEAR", "rationale": "<string>", "reasoning": "<optional>"}
  Auth: if CUPEL_AGENT_API_KEY is set in the environment it is sent as
        `Authorization: Bearer <key>`. No other host is contacted; no telemetry.
──────────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import csv
import json
import os
import urllib.request
from pathlib import Path

from agent.triage import present_alert
from common.io import read_jsonl, write_json, write_jsonl

# The exact instruction present_alert appends for OUR output contract; stripped from
# the exported prompt so the customer's agent uses its own output format.
_RETURN_INSTR = "\nReturn your triage decision as the specified JSON object."

REQUIRED_COLUMNS = ("alert_id", "decision")


class ByoCsvError(ValueError):
    """A decisions CSV that cannot be ingested. Messages name the offending row."""


# ── battery export ──────────────────────────────────────────────────────────
def battery_prompt(alert: dict) -> str:
    """The alert exactly as an agent should see it, minus Cupel's own output contract."""
    return present_alert(alert).replace(_RETURN_INSTR, "")


def load_battery(path: str | Path) -> dict[str, dict]:
    """Index the labeled battery by alert_id (labels stay server-side, never exported)."""
    return {a["alert_id"]: a for a in read_jsonl(path)}


def export_battery(alerts: list[dict], out_path: str | Path) -> int:
    """Write {alert_id, prompt} for each alert — what the customer feeds their agent.

    Deliberately omits ground_truth, gt_typology, and is_sar so the customer cannot
    train to the labels.
    """
    rows = [{"alert_id": a["alert_id"], "prompt": battery_prompt(a)} for a in alerts]
    n = write_jsonl(out_path, rows)
    # Label the export: this is the OPEN PRACTICE battery — self-scored and gameable.
    # The un-gameable held-out challenge tier is server-side (docs/CHALLENGE_PROTOCOL.md).
    write_json(Path(out_path).with_name("battery_manifest.json"), {
        "kind": "open-practice",
        "n_alerts": len(alerts),
        "note": ("Open practice battery: you hold these alerts, so a cert scored on them is "
                 "self-tested and gameable. The un-gameable held-out challenge tier is "
                 "server-side and never exported — see docs/CHALLENGE_PROTOCOL.md."),
    })
    return n


# ── logreplay ingest (zero network) ─────────────────────────────────────────
def _norm_decision(raw: str, rownum: int, alert_id: str) -> str:
    d = (raw or "").strip().upper()
    if d not in ("ESCALATE", "CLEAR"):
        raise ByoCsvError(
            f"row {rownum} (alert_id={alert_id!r}): decision must be ESCALATE or CLEAR "
            f"(case-insensitive), got {raw!r}."
        )
    return d


def _record(alert: dict, *, condition: str, decision: str, rationale: str,
            reasoning: str, seed: int, agent_label: str) -> dict:
    """Build a decision record matching agent.triage.decide()'s shape (no model call)."""
    return {
        "alert_id": alert["alert_id"],
        "condition": condition,
        "phrasing": None,
        "seed": seed,
        "decision": decision,
        "rationale": rationale,
        "reasoning": reasoning,
        "parse_ok": True,
        "agent_model": agent_label,
        "usage": {"input_tokens": 0, "output_tokens": 0, "latency_s": 0.0, "cost_usd": 0.0},
        "gt_label": alert["ground_truth"]["label"],
        "gt_typology": alert["gt_typology"],
        "narrative": alert["narrative"],
        "features": alert["features"],
        "subtle": alert.get("subtle", False),
    }


def load_logreplay_decisions(csv_path: str | Path, battery: dict[str, dict],
                             *, seed: int = 0, agent_label: str = "logreplay") -> list[dict]:
    """Parse a decisions CSV into scorable decision records. Pure file I/O — no network.

    Forgiving (case-insensitive decisions, extra columns ignored) but directive: every
    failure names the offending row and alert_id.
    """
    path = Path(csv_path)
    if not path.exists():
        raise ByoCsvError(f"decisions CSV not found: {path}")
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        cols = {(c or "").strip().lower() for c in (reader.fieldnames or [])}
        missing = [c for c in REQUIRED_COLUMNS if c not in cols]
        if missing:
            raise ByoCsvError(
                f"missing required column(s): {', '.join(missing)}. "
                f"Found columns: {sorted(cols)}. Required: {list(REQUIRED_COLUMNS)}."
            )
        records: list[dict] = []
        seen: set[tuple[str, str]] = set()
        for rownum, raw in enumerate(reader, start=2):  # row 1 is the header
            row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
            alert_id = row.get("alert_id", "")
            if not alert_id:
                raise ByoCsvError(f"row {rownum}: empty alert_id.")
            alert = battery.get(alert_id)
            if alert is None:
                raise ByoCsvError(
                    f"row {rownum}: alert_id={alert_id!r} is not in the exported battery. "
                    "Decisions must be on the Cupel battery (export it with "
                    "`uv run python -m data.build --export-battery`)."
                )
            condition = row.get("condition") or "neutral"
            key = (alert_id, condition)
            if key in seen:
                raise ByoCsvError(
                    f"row {rownum}: duplicate (alert_id={alert_id!r}, condition={condition!r})."
                )
            seen.add(key)
            records.append(_record(
                alert, condition=condition,
                decision=_norm_decision(row.get("decision", ""), rownum, alert_id),
                rationale=row.get("rationale", ""), reasoning=row.get("reasoning", ""),
                seed=seed, agent_label=agent_label,
            ))
    if not records:
        raise ByoCsvError(f"{path} has a header but no decision rows.")
    return records


# ── api ingest (BETA, black-box endpoint) ───────────────────────────────────
class ApiAgent:
    """BETA. Treats a customer endpoint as a black box (see API CONTRACT above).

    Cupel POSTs one alert and reads back {decision, rationale}; it never sends the
    customer's model anything but the alert, and contacts no other host.
    """
    name = "api"

    def __init__(self, endpoint: str, model_label: str, *, timeout: float = 60.0):
        self.endpoint = endpoint
        self.model_label = model_label or "customer-endpoint"
        self.timeout = timeout

    def _call(self, payload: dict) -> dict:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(self.endpoint, data=data,
                                     headers={"Content-Type": "application/json"})
        key = os.environ.get("CUPEL_AGENT_API_KEY")
        if key:
            req.add_header("Authorization", f"Bearer {key}")
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode())

    def triage(self, alert: dict, condition: str, phrasing: str | None) -> dict:
        try:
            out = self._call({"alert_id": alert["alert_id"],
                              "alert": battery_prompt(alert), "condition": condition})
            decision = str(out.get("decision", "")).strip().upper()
            if decision not in ("ESCALATE", "CLEAR"):
                decision = "ESCALATE"  # fail safe, same policy as the native path
            rationale, reasoning, parse_ok = str(out.get("rationale", "")), str(out.get("reasoning", "")), True
        except Exception as e:  # endpoint error: fail safe (escalate), don't abort the run
            decision, rationale, reasoning, parse_ok = "ESCALATE", f"__ENDPOINT_ERROR__: {e}", "", False
        rec = _record(alert, condition=condition, decision=decision, rationale=rationale,
                      reasoning=reasoning, seed=0, agent_label=self.model_label)
        rec["parse_ok"] = parse_ok
        return rec
