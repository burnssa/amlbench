"""Public CLI: `python -m amlbench run [--models ...] [--dry-run] ...`

`run` is the benchmark-conventional alias for the full Model × Base × Data grid; it
forwards to `eval.canonical_run` (which keeps working directly). Add new public
subcommands here, not by exposing internal module paths.
"""
from __future__ import annotations

import sys

USAGE = (
    "usage: python -m amlbench run [--dry-run] [--models <provider/model,...>] "
    "[--n-report N] [--n-benign N] [--out DIR]\n"
    "  run   Run the AMLBench leaderboard grid → results/canonical/leaderboard.json"
)


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(USAGE)
        raise SystemExit(0 if argv[:1] in ([], ["-h"], ["--help"]) else 2)
    cmd, rest = argv[0], argv[1:]
    if cmd != "run":
        print(f"unknown command: {cmd!r}\n{USAGE}")
        raise SystemExit(2)
    # Forward to the internal runner; it argparses sys.argv[1:].
    from eval.canonical_run import main as run_main

    sys.argv = ["amlbench run", *rest]
    run_main()


if __name__ == "__main__":
    main()
