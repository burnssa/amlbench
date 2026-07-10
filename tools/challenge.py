"""Held-out challenge set — protocol stub. Full design: docs/CHALLENGE_PROTOCOL.md.

The challenge set is the un-gameable tier of the trust ladder and the FRONT HALF of paid
independent attestation (same mechanism: AMLBench holds the alerts, drives the customer's
`--agent api` endpoint, scores server-side). It is structurally incompatible with
LogReplay — a set you can't pre-train to cannot be exported — so it never enters this
open-source repo.

This module is the seam. In the OSS repo the challenge set is unavailable; the hosted
AMLBench service implements load + server-side scoring. The fields that distinguish a
challenge certificate from a practice one already exist and are populated
(`finding/cert_request.py`): `battery.kind`, `battery.version`, `assurance_level`.
"""
from __future__ import annotations

# The challenge alerts/labels are server-held; they are never present in this repo.
CHALLENGE_AVAILABLE = False

# battery.kind values (the seam between the tiers; mirrored in cert_request.json).
PRACTICE = "open-practice"
CHALLENGE = "held-out-challenge"


class ChallengeUnavailable(NotImplementedError):
    """Raised when the held-out challenge path is invoked in the open-source repo."""


def require_challenge() -> None:
    """Gate the held-out branch. Raises in OSS; the hosted service overrides this path."""
    raise ChallengeUnavailable(
        "The held-out challenge set is server-held and is NOT part of the open-source "
        "repo — that is what makes it un-gameable (an exportable set can be pre-trained "
        "to). It runs through the hosted AMLBench service, which holds the alerts, drives "
        "your `--agent api` endpoint, and scores server-side. See "
        "docs/CHALLENGE_PROTOCOL.md. Until then, use the open practice battery "
        "(--export-battery + --agent logreplay), which emits an `open-practice` cert."
    )


def challenge_version() -> str:
    """The rotated challenge-set id that lands in cert_request.battery.version.

    When the real set ships this returns e.g. 'challenge-v3', so a cert against v3 reads
    differently from one against v7. Stubbed here (no set in the OSS repo).
    """
    return "unavailable"
