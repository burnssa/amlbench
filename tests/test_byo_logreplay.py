"""BYO LogReplay: proves the ingest is zero-network and the CSV parse is forgiving + directive.

Plain runnable script (matches tests/offline_smoke.py — no pytest dependency):

    uv run python tests/test_byo_logreplay.py
"""
from __future__ import annotations

import socket
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.byo import ByoCsvError, load_battery, load_logreplay_decisions
from common.netguard import NetworkAccessError, no_network

BATTERY = "data/alerts.jsonl"
SAMPLE = "samples/sample_decisions.csv"


def _csv(text: str) -> str:
    p = Path(tempfile.mkdtemp()) / "d.csv"
    p.write_text(text)
    return str(p)


def test_logreplay_makes_zero_network_calls(battery):
    # The one-liner that matters: scoring a decisions CSV touches no network.
    with no_network():
        records = load_logreplay_decisions(SAMPLE, battery)
    assert records, "no records parsed"
    assert all(r["decision"] in ("ESCALATE", "CLEAR") for r in records)
    assert all("gt_label" in r for r in records), "records not joined to battery ground truth"


def test_no_network_guard_actually_blocks(_battery):
    try:
        with no_network():
            socket.create_connection(("example.com", 80), timeout=1)
    except NetworkAccessError:
        return
    raise AssertionError("no_network() did not block the outbound connection")


def test_decision_is_case_insensitive_and_extra_cols_ignored(battery):
    aid = next(iter(battery))
    recs = load_logreplay_decisions(_csv(f"alert_id,decision,extra\n{aid},escalate,ignored\n"), battery)
    assert recs[0]["decision"] == "ESCALATE"


def test_unknown_alert_id_names_the_row(battery):
    try:
        load_logreplay_decisions(_csv("alert_id,decision\nNOPE-9999,CLEAR\n"), battery)
    except ByoCsvError as e:
        assert "row 2" in str(e) and "NOPE-9999" in str(e)
        return
    raise AssertionError("unknown alert_id did not raise")


def test_bad_decision_value_names_the_row(battery):
    aid = next(iter(battery))
    try:
        load_logreplay_decisions(_csv(f"alert_id,decision\n{aid},MAYBE\n"), battery)
    except ByoCsvError as e:
        assert "row 2" in str(e) and "MAYBE" in str(e)
        return
    raise AssertionError("bad decision value did not raise")


def test_missing_required_column_is_directive(battery):
    try:
        load_logreplay_decisions(_csv("alert_id,verdict\nX,CLEAR\n"), battery)
    except ByoCsvError as e:
        assert "decision" in str(e)
        return
    raise AssertionError("missing required column did not raise")


def main() -> None:
    battery = load_battery(BATTERY)
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t(battery)
        print(f"  ok  {t.__name__}")
    print(f"[byo tests] {len(tests)} passed")


if __name__ == "__main__":
    main()
