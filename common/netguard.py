"""A hard guarantee that a block of code makes no outbound network calls.

The LogReplay path is the lowest-trust on-ramp: a customer scores their agent's
decisions locally and nothing about their data leaves the machine. That claim has to
be enforceable, not just asserted — `no_network()` blocks outbound TCP for its
duration so the guarantee is testable (see tests/test_byo_logreplay.py).
"""
from __future__ import annotations

import contextlib
import socket


class NetworkAccessError(RuntimeError):
    """Raised when code inside a no_network() block attempts an outbound connection."""


@contextlib.contextmanager
def no_network():
    """Block outbound socket connections for the duration of the block.

    Patches the two entry points every HTTP client ultimately calls
    (`socket.socket.connect` and `socket.create_connection`). Local/offline work —
    file I/O, CPU — is unaffected; any attempt to reach the network raises
    NetworkAccessError.
    """
    def _blocked(*_args, **_kwargs):
        raise NetworkAccessError(
            "outbound network access is blocked here — this path must run fully offline"
        )

    orig_connect = socket.socket.connect
    orig_create = socket.create_connection
    socket.socket.connect = _blocked          # type: ignore[assignment]
    socket.create_connection = _blocked        # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket.connect = orig_connect   # type: ignore[assignment]
        socket.create_connection = orig_create  # type: ignore[assignment]
