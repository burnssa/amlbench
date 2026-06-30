"""A pure-Python port of AMLSim's typology-graph generator + temporal emitter.

Why a port: AMLSim is two layers — (1) a Python layer
(`scripts/transaction_graph_generator.py`, `add_aml_typology()`) that builds the
account graph and lays down money-laundering *typology* subgraphs with SAR
labels, driven by an `alertPatterns.csv` whose columns are
`count,type,min_accounts,max_accounts,min_amount,max_amount,min_period,max_period,is_sar`;
and (2) a Java/MASON layer that mechanically steps those scheduled edges into a
timestamped transaction stream with running balances. The AML *semantics* live
in layer 1; layer 2 is mechanical. This module reproduces both in Python so the
PoC is seeded and reproducible from one command, with no JVM.

Typology type strings mirror AMLSim's `alert_types`:
    {fan_out, fan_in, cycle, bipartite, stack, random, scatter_gather, gather_scatter}
This port implements the subset the PoC uses (fan_in, fan_out, cycle,
gather_scatter) plus normal-model background traffic. Structuring/smurfing is a
`fan_in` of sub-threshold cash deposits — AMLSim-native provenance for our
target class.

Fidelity to AMLSim is checked against its real committed sample output by
`tools/amlsim_fidelity.py` (schema, cash/non-cash split, type vocabulary, typology
graph shapes, SAR labeling). Direct ingestion of a real AMLSim Java run
(`substrate: csv`, see build.py) is a planned seam, currently stubbed.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

# Transaction types in the spirit of AMLSim / PaySim output.
CASH_IN = "CASH_IN"      # cash deposit crediting the destination account
CASH_OUT = "CASH_OUT"    # cash withdrawal debiting the source account
TRANSFER = "TRANSFER"
PAYMENT = "PAYMENT"

COUNTRIES_NORMAL = ["US", "US", "US", "GB", "CA", "DE", "SG", "AU", "FR"]
HIGH_RISK = ["IR", "KP", "SY", "MM"]
PROFILES = ["retail_individual", "small_business", "payroll_employer", "vendor_supplier"]


@dataclass
class Account:
    acct_id: str
    kind: str           # individual | business
    country: str
    profile: str
    balance: float


@dataclass
class Tx:
    tx_id: str
    ts: datetime
    amount: float
    src: str            # account id or "CASH"/"EXT"
    dst: str
    tx_type: str
    is_cash: bool
    # Provenance carried from the typology layer (used for labels + reconciliation):
    alert_id: str | None = None
    typology: str = "normal"
    is_sar: int = 0
    # Filled by the temporal emitter:
    src_bal_after: float | None = None
    dst_bal_after: float | None = None
    counterparty_country: str | None = None


@dataclass
class Substrate:
    accounts: dict[str, Account]
    txns: list[Tx]
    # alert_id -> dict(focal, typology, is_sar, member_accounts, ts_range)
    alerts: dict[str, dict] = field(default_factory=dict)


class _IdGen:
    def __init__(self) -> None:
        self.tx = 0

    def next_tx(self) -> str:
        self.tx += 1
        return f"TX{self.tx:07d}"


def _rand_dt(rng: random.Random, start: date, end: date) -> datetime:
    span = (end - start).days
    d = start + timedelta(days=rng.randint(0, max(span, 0)))
    return datetime(d.year, d.month, d.day, rng.randint(0, 23), rng.randint(0, 59))


def _make_accounts(rng: random.Random, n: int) -> dict[str, Account]:
    accts: dict[str, Account] = {}
    for i in range(n):
        profile = rng.choice(PROFILES)
        kind = "business" if profile in ("payroll_employer", "vendor_supplier", "small_business") else "individual"
        # A small share of accounts touch high-risk jurisdictions.
        country = rng.choice(HIGH_RISK) if rng.random() < 0.05 else rng.choice(COUNTRIES_NORMAL)
        bal = round(rng.lognormvariate(10.0, 0.9), 2)  # ~ $20k median, heavy tail
        aid = f"A{i:05d}"
        accts[aid] = Account(aid, kind, country, profile, bal)
    return accts


# ── Typology subgraph builders ────────────────────────────────────────────
# Each returns a list of (src, dst) "scheduled edges" plus the focal account.
# The temporal emitter assigns timestamps, amounts, balances afterwards.


def _normal_traffic(rng, accts, ids, cfg, txns):
    """Background normal-model traffic: each account sends a handful of txns."""
    lo, hi = cfg["amlsim"]["background_txns_per_account"]
    start = date.fromisoformat(cfg["amlsim"]["start_date"])
    end = date.fromisoformat(cfg["amlsim"]["end_date"])
    acct_ids = list(accts.keys())
    for aid, acct in accts.items():
        for _ in range(rng.randint(lo, hi)):
            dst = rng.choice(acct_ids)
            if dst == aid:
                continue
            # Amounts well below the CTR threshold for ordinary activity.
            amount = round(min(rng.lognormvariate(7.6, 0.8), 9500), 2)
            ttype = rng.choices([TRANSFER, PAYMENT, CASH_IN, CASH_OUT], weights=[4, 4, 1, 1])[0]
            is_cash = ttype in (CASH_IN, CASH_OUT)
            txns.append(
                Tx(
                    tx_id=ids.next_tx(),
                    ts=_rand_dt(rng, start, end),
                    amount=amount,
                    src=aid if ttype in (TRANSFER, PAYMENT, CASH_OUT) else "CASH",
                    dst=dst if ttype in (TRANSFER, PAYMENT) else aid,
                    tx_type=ttype,
                    is_cash=is_cash,
                    typology="normal",
                    is_sar=0,
                    counterparty_country=accts[dst].country,
                )
            )


def _emit_pattern(rng, accts, ids, cfg, txns, alerts, spec: dict):
    """Generate `spec['count']` instances of one typology pattern."""
    start = date.fromisoformat(cfg["amlsim"]["start_date"])
    end = date.fromisoformat(cfg["amlsim"]["end_date"])
    acct_ids = list(accts.keys())
    margin_ratio = 0.9

    for c in range(spec["count"]):
        n_acc = rng.randint(spec["min_accounts"], spec["max_accounts"])
        members = rng.sample(acct_ids, min(n_acc, len(acct_ids)))
        period = rng.randint(spec["min_period"], spec["max_period"])
        p_start = start + timedelta(days=rng.randint(0, max((end - start).days - period, 0)))
        p_end = p_start + timedelta(days=period)
        alert_id = f"{spec['typology'].upper()}-{c:04d}"
        typ = spec["type"]
        cash = spec.get("cash", False)

        def amt() -> float:
            return round(rng.uniform(spec["min_amount"], spec["max_amount"]), 2)

        def when() -> datetime:
            return _rand_dt(rng, p_start, p_end)

        edges: list[Tx] = []

        if typ == "fan_in":
            # Many originators -> one hub (focal). Structuring = cash deposits.
            hub = members[0]
            for orig in members[1:]:
                edges.append(
                    Tx(ids.next_tx(), when(), amt(),
                       src=("CASH" if cash else orig), dst=hub,
                       tx_type=(CASH_IN if cash else TRANSFER), is_cash=cash,
                       alert_id=alert_id, typology=spec["typology"], is_sar=spec["is_sar"],
                       counterparty_country=accts[orig].country)
                )
            focal = hub
            if spec.get("subtle"):
                # Make the focal a plausibly cash-accepting small business and bury
                # the sub-threshold deposits in routine activity so the structuring
                # pattern must be inferred, not read off a flag.
                accts[hub].profile = "small_business"
                others = [a for a in acct_ids if a != hub]
                # one legit large inbound transfer (e.g. an invoice settlement)
                edges.append(Tx(ids.next_tx(), when(), round(rng.uniform(12000, 40000), 2),
                                src=rng.choice(others), dst=hub, tx_type=TRANSFER, is_cash=False,
                                alert_id=alert_id, typology=spec["typology"], is_sar=0,
                                counterparty_country=accts[hub].country))
                # one small below-band cash deposit (noise in the cash channel)
                edges.append(Tx(ids.next_tx(), when(), round(rng.uniform(500, 4000), 2),
                                src="CASH", dst=hub, tx_type=CASH_IN, is_cash=True,
                                alert_id=alert_id, typology=spec["typology"], is_sar=0,
                                counterparty_country=accts[hub].country))
                # a couple of ordinary outgoing payments (rent / suppliers)
                for _ in range(2):
                    edges.append(Tx(ids.next_tx(), when(), round(rng.uniform(2000, 8000), 2),
                                    src=hub, dst=rng.choice(others), tx_type=TRANSFER, is_cash=False,
                                    alert_id=alert_id, typology=spec["typology"], is_sar=0,
                                    counterparty_country=accts[hub].country))

        elif typ == "fan_out":
            # One hub (focal) -> many beneficiaries.
            hub = members[0]
            for benef in members[1:]:
                edges.append(
                    Tx(ids.next_tx(), when(), amt(),
                       src=hub, dst=benef,
                       tx_type=(CASH_OUT if cash else TRANSFER), is_cash=cash,
                       alert_id=alert_id, typology=spec["typology"], is_sar=spec["is_sar"],
                       counterparty_country=accts[benef].country)
                )
            focal = hub

        elif typ == "cycle":
            # a -> b -> c -> a, amounts decaying by margin_ratio (layering). Focal = a.
            base = amt()
            ring = members + [members[0]]
            a = base
            for i in range(len(ring) - 1):
                edges.append(
                    Tx(ids.next_tx(), when(), round(a, 2),
                       src=ring[i], dst=ring[i + 1],
                       tx_type=TRANSFER, is_cash=False,
                       alert_id=alert_id, typology=spec["typology"], is_sar=spec["is_sar"],
                       counterparty_country=accts[ring[i + 1]].country)
                )
                a *= margin_ratio
            focal = members[0]

        elif typ == "gather_scatter":
            # originators -> hub (gather), then hub -> beneficiaries (scatter).
            half = max(1, (len(members) - 1) // 2)
            hub = members[0]
            origs = members[1 : 1 + half]
            benefs = members[1 + half :] or [members[-1]]
            mid = p_start + timedelta(days=period / 2)
            for orig in origs:
                edges.append(
                    Tx(ids.next_tx(), _rand_dt(rng, p_start, mid), amt(),
                       src=orig, dst=hub, tx_type=TRANSFER, is_cash=False,
                       alert_id=alert_id, typology=spec["typology"], is_sar=spec["is_sar"],
                       counterparty_country=accts[orig].country)
                )
            for benef in benefs:
                edges.append(
                    Tx(ids.next_tx(), _rand_dt(rng, mid, p_end), round(amt() * margin_ratio, 2),
                       src=hub, dst=benef, tx_type=TRANSFER, is_cash=False,
                       alert_id=alert_id, typology=spec["typology"], is_sar=spec["is_sar"],
                       counterparty_country=accts[benef].country)
                )
            focal = hub
        else:
            raise ValueError(f"unsupported typology type: {typ}")

        txns.extend(edges)
        alerts[alert_id] = {
            "focal": focal,
            "typology": spec["typology"],
            "is_sar": spec["is_sar"],
            "subtle": spec.get("subtle", False),
            "members": members,
            "ts_start": p_start.isoformat(),
            "ts_end": p_end.isoformat(),
        }


def _emit_balances(accts: dict[str, Account], txns: list[Tx]) -> None:
    """The 'Java/MASON' step: walk transactions in time order, track balances."""
    bal = {a.acct_id: a.balance for a in accts.values()}
    for tx in sorted(txns, key=lambda t: t.ts):
        if tx.src in bal:
            bal[tx.src] = round(bal[tx.src] - tx.amount, 2)
            tx.src_bal_after = bal[tx.src]
        if tx.dst in bal:
            bal[tx.dst] = round(bal[tx.dst] + tx.amount, 2)
            tx.dst_bal_after = bal[tx.dst]


def generate_substrate(cfg: dict, seed: int) -> Substrate:
    """Build accounts + background traffic + typology patterns, then emit balances."""
    rng = random.Random(seed)
    ids = _IdGen()
    accts = _make_accounts(rng, cfg["amlsim"]["background_accounts"])
    txns: list[Tx] = []
    alerts: dict[str, dict] = {}

    _normal_traffic(rng, accts, ids, cfg, txns)
    for spec in cfg["amlsim"]["alert_patterns"]:
        _emit_pattern(rng, accts, ids, cfg, txns, alerts, spec)

    _emit_balances(accts, txns)
    return Substrate(accounts=accts, txns=txns, alerts=alerts)
