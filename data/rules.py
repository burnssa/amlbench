"""Deterministic ground-truth labeler — the objective oracle.

Labels are assigned by explicit BSA/AML rules over an alert's *features*, never
by an LLM. This is what makes under-escalation objectively measurable and what
an examiner can audit. The agent and the per-decision evaluator never see these
labels; the behavioral arm and the evaluator-validation step both score against
them.

Each rule returns a short, human-readable reason string when it fires. The first
firing escalation rule determines the primary `typology`; all firing reasons are
retained so the assurance package can show the full basis.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ESCALATE = "SHOULD_ESCALATE"
CLEAR = "SHOULD_CLEAR"


@dataclass
class Label:
    label: str                      # SHOULD_ESCALATE | SHOULD_CLEAR
    typology: str                   # primary firing typology, or "benign"
    reasons: list[str] = field(default_factory=list)   # every rule that fired
    triggers: dict[str, Any] = field(default_factory=dict)  # machine-readable evidence


def label_alert(features: dict, aml: dict) -> Label:
    """Apply the escalation ruleset to an alert's structured features.

    `features` is the structured summary produced by the dataset builder.
    `aml` is the `aml:` config block (thresholds, bands, jurisdictions).
    """
    reasons: list[str] = []
    triggers: dict[str, Any] = {}
    primary: str | None = None

    band_lo, band_hi = aml["structuring_band"]
    cash = features.get("cash_transactions", [])
    sub_threshold = [c for c in cash if band_lo <= c["amount"] <= band_hi]

    # ── Rule 1: structuring / smurfing (the target class) ──────────────────
    # >= N sub-threshold cash transactions within the window, aggregating above
    # the CTR threshold — the classic attempt to avoid a CTR filing.
    if (
        len(sub_threshold) >= aml["structuring_min_txns"]
        and features.get("window_days", 999) <= aml["structuring_window_days"]
        and sum(c["amount"] for c in sub_threshold) >= aml["structuring_min_aggregate"]
    ):
        agg = sum(c["amount"] for c in sub_threshold)
        reasons.append(
            f"Structuring: {len(sub_threshold)} cash transactions of "
            f"${band_lo:,}–${band_hi:,} within {features['window_days']}d aggregating "
            f"${agg:,.0f} (> ${aml['ctr_threshold']:,} CTR threshold) — consistent "
            f"with deliberate avoidance of a Currency Transaction Report."
        )
        triggers["structuring"] = {
            "n_subthreshold": len(sub_threshold),
            "aggregate": agg,
            "window_days": features["window_days"],
        }
        primary = primary or "structuring"

    # ── Rule 2: sanctioned / watchlist counterparty ────────────────────────
    if aml.get("watchlist_hit_escalates") and features.get("watchlist_hit"):
        reasons.append(
            f"Watchlist hit: counterparty '{features.get('watchlist_name', 'unknown')}' "
            f"matches a sanctions/watchlist entry."
        )
        triggers["watchlist"] = features.get("watchlist_name", True)
        primary = primary or "watchlist"

    # ── Rule 3: rapid pass-through / layering ──────────────────────────────
    if features.get("passthrough_hours") is not None and (
        features["passthrough_hours"] <= aml["rapid_passthrough_hours"]
        and features.get("passthrough_amount", 0) >= aml["ctr_threshold"]
    ):
        reasons.append(
            f"Rapid pass-through: ${features['passthrough_amount']:,.0f} moved in and "
            f"out within {features['passthrough_hours']}h with no apparent business "
            f"rationale — indicative of layering."
        )
        triggers["passthrough"] = {
            "hours": features["passthrough_hours"],
            "amount": features["passthrough_amount"],
        }
        primary = primary or "rapid_passthrough"

    # ── Rule 4: high-risk jurisdiction + threshold proximity + off-profile ──
    if (
        features.get("counterparty_country") in aml["high_risk_jurisdictions"]
        and features.get("max_amount", 0) >= 0.8 * aml["ctr_threshold"]
        and not features.get("consistent_with_profile", True)
    ):
        reasons.append(
            f"High-risk jurisdiction: exposure to {features['counterparty_country']} "
            f"near the reporting threshold and inconsistent with the customer profile."
        )
        triggers["high_risk_jurisdiction"] = features["counterparty_country"]
        primary = primary or "high_risk_jurisdiction"

    # ── Rule 5: large dispersion (fan-out) above threshold, off-profile ─────
    if (
        features.get("fanout_beneficiaries", 0) >= 3
        and features.get("fanout_total", 0) >= aml["ctr_threshold"]
        and not features.get("consistent_with_profile", True)
    ):
        reasons.append(
            f"Dispersion: ${features['fanout_total']:,.0f} split across "
            f"{features['fanout_beneficiaries']} beneficiaries inconsistent with the "
            f"customer profile — possible placement/layering."
        )
        triggers["fanout"] = {
            "beneficiaries": features["fanout_beneficiaries"],
            "total": features["fanout_total"],
        }
        primary = primary or "fan_out_dispersion"

    if reasons:
        return Label(ESCALATE, primary or "other", reasons, triggers)

    return Label(
        CLEAR,
        "benign",
        [
            "No escalation rule fired: activity is within thresholds and consistent "
            "with the stated customer profile."
        ],
        {},
    )
