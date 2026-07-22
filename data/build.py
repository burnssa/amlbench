"""Turn the AMLSim-derived substrate into a labeled alert dataset.

Pipeline:  substrate (accounts + timestamped txns + typology tags)
        -> per-focal-account windows  -> structured features + templated narrative
        -> deterministic ground-truth label (rules.label_alert)
        -> alerts.jsonl

The narrative is templated directly from the simulated transactions (no LLM) so
the dataset is fully reproducible and free to regenerate; AMLSim's `is_sar` flag
is carried alongside the rule label for reconciliation/reporting.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta

from common.config import load_config, resolve
from common.io import write_jsonl
from data import amlsim, rules
from data.amlsim import CASH_IN, CASH_OUT, Substrate, Tx


def _txns_touching(focal: str, txns: list[Tx], start: datetime, end: datetime) -> list[Tx]:
    return [t for t in txns if (t.src == focal or t.dst == focal) and start <= t.ts <= end]


def extract_features(
    focal: str,
    win_txns: list[Tx],
    accts: dict,
    window_days: int,
    aml: dict,
    consistent_with_profile: bool,
) -> dict:
    """Build the structured feature view a monitoring system would surface."""
    inflow = [t for t in win_txns if t.dst == focal]
    outflow = [t for t in win_txns if t.src == focal]
    cash_in = [t for t in inflow if t.tx_type == CASH_IN]

    cash_transactions = [{"amount": t.amount, "ts": t.ts.isoformat()} for t in cash_in]
    amounts = [t.amount for t in win_txns] or [0.0]

    # Rapid pass-through: a large amount in and a large amount out within the
    # rapid window. O(n^2) over a handful of window txns.
    ctr = aml["ctr_threshold"]
    big_in = [t for t in inflow if t.amount >= ctr]
    big_out = [t for t in outflow if t.amount >= ctr]
    passthrough_hours = None
    passthrough_amount = 0.0
    best_gap = None
    for ti in big_in:
        for to in big_out:
            gap = abs((to.ts - ti.ts).total_seconds()) / 3600.0
            if gap <= aml["rapid_passthrough_hours"] and (best_gap is None or gap < best_gap):
                best_gap = gap
                passthrough_hours = round(gap, 1)
                passthrough_amount = round(min(ti.amount, to.amount), 2)

    # Dispersion (fan-out): distinct beneficiary accounts the focal paid.
    benef = {t.dst for t in outflow if t.dst in accts and t.dst != focal}
    fanout_total = round(sum(t.amount for t in outflow if t.dst in benef), 2)

    # Representative counterparty country: prefer a high-risk hit if present.
    countries = [t.counterparty_country for t in win_txns if t.counterparty_country]
    hr = next((c for c in countries if c in aml["high_risk_jurisdictions"]), None)
    # Deterministic predominant country: most frequent, ties broken alphabetically
    # (sorted() makes this independent of PYTHONHASHSEED set ordering, so the battery
    # — and therefore its hash, which certificates pin to — is reproducible).
    counterparty_country = hr or (max(sorted(set(countries)), key=countries.count) if countries else None)

    return {
        "n_transactions": len(win_txns),
        "window_days": window_days,
        "total_inflow": round(sum(t.amount for t in inflow), 2),
        "total_outflow": round(sum(t.amount for t in outflow), 2),
        "max_amount": round(max(amounts), 2),
        "cash_transactions": cash_transactions,
        "n_cash_in": len(cash_in),
        "passthrough_hours": passthrough_hours,
        "passthrough_amount": passthrough_amount,
        "fanout_beneficiaries": len(benef),
        "fanout_total": fanout_total,
        "counterparty_country": counterparty_country,
        "watchlist_hit": False,  # not modeled in this PoC substrate
        "consistent_with_profile": consistent_with_profile,
        # Raw per-transaction ledger (for alerts presented as a ledger rather than a
        # pre-digested summary — the agent must infer patterns from it). `ts`,
        # `counterparty`, `counterparty_country` carry what a real ledger row shows;
        # without them a ledger-only presentation can't decide the pass-through
        # (needs hour gaps), dispersion (distinct beneficiaries), or jurisdiction
        # (counterparty country) rules. The subtle narrative renders only
        # date/type/amount/direction, so v0 prompt text is unchanged.
        "transactions": [
            {"date": t.ts.strftime("%Y-%m-%d"), "ts": t.ts.strftime("%Y-%m-%d %H:%M"),
             "type": t.tx_type, "amount": round(t.amount, 2),
             "direction": "in" if t.dst == focal else "out",
             "counterparty": t.src if t.dst == focal else t.dst,
             "counterparty_country": t.counterparty_country}
            for t in sorted(win_txns, key=lambda x: x.ts)
        ],
    }


def render_narrative(alert_id, focal_acct, features: dict, subtle: bool = False) -> str:
    """A compliance-style alert summary, templated from the features.

    `subtle=True` produces a realistic, non-pre-digested alert: the activity is
    presented as a raw transaction ledger with no red flag called out, so the
    structuring pattern must be inferred from the data rather than read off a
    summary line. Used for the `structuring_subtle` class.
    """
    f = features
    header = (
        f"ALERT {alert_id} — account {focal_acct.acct_id} "
        f"({focal_acct.kind}, profile: {focal_acct.profile}, domicile: {focal_acct.country}). "
        f"Review window: {f['window_days']} day(s); {f['n_transactions']} transactions in scope. "
        f"Total inflow ${f['total_inflow']:,.0f}; total outflow ${f['total_outflow']:,.0f}; "
        f"largest single transaction ${f['max_amount']:,.0f}."
    )

    if subtle:
        # Routine-sounding alert + a raw ledger. No flagged cash-deposit line, no
        # profile-deviation callout — the analyst must spot the pattern themselves.
        ledger = "; ".join(
            f"{t['date']} {t['type']} ${t['amount']:,.0f} ({t['direction']})"
            for t in f.get("transactions", [])
        )
        return (
            f"{header} Routine periodic review of account activity. "
            f"Transaction ledger for the window: {ledger}. "
            f"No prior dispositions on file."
        )

    lines = [header]
    if f["cash_transactions"]:
        amts = ", ".join(f"${c['amount']:,.0f}" for c in f["cash_transactions"])
        lines.append(f"Cash deposits received ({f['n_cash_in']}): {amts}.")
    if f["passthrough_hours"] is not None:
        lines.append(
            f"A large credit and offsetting debit (~${f['passthrough_amount']:,.0f}) "
            f"occurred within {f['passthrough_hours']}h of each other."
        )
    if f["fanout_beneficiaries"] >= 2:
        lines.append(
            f"Outgoing funds were dispersed to {f['fanout_beneficiaries']} distinct "
            f"beneficiaries totaling ${f['fanout_total']:,.0f}."
        )
    if f["counterparty_country"]:
        lines.append(f"Predominant counterparty domicile: {f['counterparty_country']}.")
    lines.append(
        "Activity is consistent with the customer's expected profile."
        if f["consistent_with_profile"]
        else "Activity DEVIATES from the customer's expected profile."
    )
    return " ".join(lines)


def build_alerts(cfg, sub: Substrate) -> list[dict]:
    aml = cfg["aml"]
    accts = sub.accounts
    alerts: list[dict] = []
    by_alert = defaultdict(list)
    for t in sub.txns:
        if t.alert_id:
            by_alert[t.alert_id].append(t)

    sar_focals = set()

    # 1) Pattern alerts (SAR typologies + benign decoys).
    for alert_id, meta in sub.alerts.items():
        focal = meta["focal"]
        sar_focals.add(focal)
        start = datetime.fromisoformat(meta["ts_start"])
        end = datetime.fromisoformat(meta["ts_end"]) + timedelta(hours=23, minutes=59)
        win = _txns_touching(focal, sub.txns, start, end)
        window_days = max(1, (end.date() - start.date()).days)
        subtle = meta.get("subtle", False)
        # benign patterns are on-profile; subtle structuring is presented as on-profile
        # (cash receipts plausible for a small business) so the pattern isn't pre-flagged.
        consistent = (meta["is_sar"] == 0) or subtle
        feats = extract_features(focal, win, accts, window_days, aml, consistent)
        gt = rules.label_alert(feats, aml)
        alerts.append(
            {
                "alert_id": alert_id,
                "gt_typology": meta["typology"],
                "is_sar_amlsim": meta["is_sar"],
                "subtle": subtle,
                "focal_account": focal,
                "focal_profile": accts[focal].profile,
                "focal_country": accts[focal].country,
                "window_days": window_days,
                "features": feats,
                "narrative": render_narrative(alert_id, accts[focal], feats, subtle=subtle),
                "ground_truth": {
                    "label": gt.label,
                    "typology": gt.typology,
                    "reasons": gt.reasons,
                    "triggers": gt.triggers,
                },
            }
        )

    # 2) Normal-traffic CLEAR alerts to reach the target N (a realistic queue is
    #    mostly benign). Sample focal accounts not involved in any SAR pattern.
    import random

    rng = random.Random(99)
    target = cfg["dataset"]["n_alerts"]
    need = max(0, target - len(alerts))
    candidates = [a for a in accts if a not in sar_focals]
    rng.shuffle(candidates)
    txns_by_acct = defaultdict(list)
    for t in sub.txns:
        if t.typology == "normal":
            if t.src in accts:
                txns_by_acct[t.src].append(t)
            if t.dst in accts:
                txns_by_acct[t.dst].append(t)

    made = 0
    for focal in candidates:
        if made >= need:
            break
        ts = sorted(txns_by_acct.get(focal, []), key=lambda t: t.ts)
        if len(ts) < 2:
            continue
        anchor = ts[len(ts) // 2].ts
        start = anchor - timedelta(days=7)
        end = anchor + timedelta(days=7)
        win = _txns_touching(focal, sub.txns, start, end)
        if len(win) < 2:
            continue
        feats = extract_features(focal, win, accts, 14, aml, consistent_with_profile=True)
        gt = rules.label_alert(feats, aml)
        alert_id = f"NORM-{made:04d}"
        alerts.append(
            {
                "alert_id": alert_id,
                "gt_typology": "normal",
                "is_sar_amlsim": 0,
                "subtle": False,
                "focal_account": focal,
                "focal_profile": accts[focal].profile,
                "focal_country": accts[focal].country,
                "window_days": 14,
                "features": feats,
                "narrative": render_narrative(alert_id, accts[focal], feats),
                "ground_truth": {
                    "label": gt.label,
                    "typology": gt.typology,
                    "reasons": gt.reasons,
                    "triggers": gt.triggers,
                },
            }
        )
        made += 1

    return alerts


def summarize(alerts: list[dict]) -> dict:
    n = len(alerts)
    esc = [a for a in alerts if a["ground_truth"]["label"] == rules.ESCALATE]
    struct = [a for a in esc if a["gt_typology"].startswith("structuring")]
    # Reconciliation: do AMLSim is_sar flags agree with our rule labels?
    sar_and_esc = sum(1 for a in alerts if a["is_sar_amlsim"] == 1 and a["ground_truth"]["label"] == rules.ESCALATE)
    sar_total = sum(1 for a in alerts if a["is_sar_amlsim"] == 1)
    by_typ = defaultdict(lambda: [0, 0])
    for a in alerts:
        by_typ[a["gt_typology"]][0] += 1
        if a["ground_truth"]["label"] == rules.ESCALATE:
            by_typ[a["gt_typology"]][1] += 1
    return {
        "n_alerts": n,
        "n_escalate": len(esc),
        "escalate_rate": round(len(esc) / n, 3) if n else 0,
        "n_structuring": len(struct),
        "structuring_share_of_escalate": round(len(struct) / len(esc), 3) if esc else 0,
        "amlsim_sar_recovered_by_rules": f"{sar_and_esc}/{sar_total}",
        "by_typology": {k: {"n": v[0], "escalate": v[1]} for k, v in sorted(by_typ.items())},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--config", default=None)
    ap.add_argument("--export-battery", nargs="?", const="results/byo/battery.jsonl", default=None,
                    metavar="PATH",
                    help="also export {alert_id, prompt} (NO labels) for a BYO agent to run")
    args = ap.parse_args()

    cfg = load_config(args.config)
    seed = args.seed if args.seed is not None else cfg["run"]["core_seed"]

    if cfg["dataset"]["substrate"] == "csv":
        raise NotImplementedError(
            "CSV ingestion of a real AMLSim Java run is stubbed; set substrate: amlsim_port."
        )
    sub = amlsim.generate_substrate(cfg, seed)
    alerts = build_alerts(cfg, sub)

    out = resolve(cfg["dataset"]["output"])
    write_jsonl(out, alerts)

    if args.export_battery is not None:
        from agent.byo import export_battery
        bpath = resolve(args.export_battery)
        n = export_battery(alerts, bpath)
        print(f"[data] exported {n} OPEN-PRACTICE battery prompts (no labels) -> {bpath}\n"
              f"       (open-practice = self-scored & gameable; the un-gameable held-out\n"
              f"        challenge tier is server-side — see docs/CHALLENGE_PROTOCOL.md)\n"
              f"       run these through your agent, then score the decisions CSV with\n"
              f"       `uv run python run.py --agent logreplay --decisions <your.csv>`")

    summ = summarize(alerts)
    print(f"[data] seed={seed} substrate=amlsim_port -> {out}")
    for k, v in summ.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
