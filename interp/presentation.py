"""Ledger-mode alert presentation for the interp experiment.

Renders EVERY alert the way the v0 pipeline renders `structuring_subtle`: header
facts + a screening line + the raw transaction ledger. No derived extract lines
(pre-grouped cash amounts, pre-paired pass-through, dispersion totals), no
structured-indicators block, and no profile-consistency verdict — for non-subtle
alerts that verdict line correlates with the ground-truth label, so probes
trained on the standard presentation could read a flag instead of computed
suspicion. In ledger mode the extraction AND the judgment are the model's job.

Information-completeness: every input the deterministic rules consume is still
derivable — cash deposits and their dates from the rows (structuring), hour
gaps from row timestamps (pass-through), distinct beneficiary counterparties
(dispersion), per-row counterparty country (jurisdiction), and the screening
line (watchlist). The screening line stays because sanctions screening is a
separate system's factual output, not a judgment about the pattern.

Interp-only: `agent/triage.py::present_alert` (the v0 presentation) is
untouched; ledger-mode results are NOT comparable to the v0 leaderboard and get
their own baseline pass. For subtle alerts the two modes near-coincide (the
ledger rows gain timestamps/counterparties) — a built-in consistency check.
"""
from __future__ import annotations


def _row(t: dict) -> str:
    ts = t.get("ts", t["date"])
    amt = f"${t['amount']:,.0f}"
    cp = t.get("counterparty")
    country = t.get("counterparty_country")
    cp_str = f"{cp} ({country})" if cp and country else (cp or "")
    if t["direction"] == "in":
        tail = f" (in, from {cp_str})" if cp_str else " (in)"
    else:
        tail = f" (out → {cp_str})" if cp_str else " (out)"
    return f"{ts} {t['type']} {amt}{tail}"


def render_ledger_narrative(alert: dict) -> str:
    """Ledger-mode narrative for any alert (mirrors the subtle template's shape)."""
    f = alert["features"]
    header = (
        f"ALERT {alert['alert_id']} — account {alert['focal_account']} "
        f"({'individual' if alert['focal_profile'] == 'retail_individual' else 'business'}, "
        f"profile: {alert['focal_profile']}, domicile: {alert['focal_country']}). "
        f"Review window: {f['window_days']} day(s); {f['n_transactions']} transactions in scope. "
        f"Total inflow ${f['total_inflow']:,.0f}; total outflow ${f['total_outflow']:,.0f}; "
        f"largest single transaction ${f['max_amount']:,.0f}."
    )
    screening = (
        "Sanctions/watchlist screening: HIT on a counterparty."
        if f.get("watchlist_hit")
        else "Sanctions/watchlist screening: no hits."
    )
    ledger = "; ".join(_row(t) for t in f.get("transactions", []))
    return (
        f"{header} Routine periodic review of account activity. {screening} "
        f"Transaction ledger for the window: {ledger}. "
        f"No prior dispositions on file."
    )


def present_alert_ledger(alert: dict) -> str:
    """Full user-turn text: ledger narrative + the decision instruction.

    Deliberately no structured-indicators block and no pre-extracted amounts —
    the counterpart of agent/triage.py::present_alert for ledger mode.
    """
    return (
        render_ledger_narrative(alert)
        + "\n\nReturn your triage decision as the specified JSON object."
    )
