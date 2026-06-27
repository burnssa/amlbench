"""Verifiable self-certification — cryptographic primitive (prototype).

Demonstrates the "cryptographic indicator" in the open-core trust ladder
(docs/SELF_CERT_DESIGN.md): the provider scores a run and issues an Ed25519-signed
certificate over a canonical manifest of the metrics. Anyone can verify the
signature against the provider's PUBLISHED public key — so the certificate is
tamper-evident and provenance-bound, without the verifier trusting the holder.

What this proves: the certificate is authentic and unaltered, and (in the full
design) the metrics were computed by the provider on a hidden challenge.
What it does NOT prove: that the holder ran their real production agent — that gap
is closed only by the paid live engagement.

    python -m tools.certify keygen
    python -m tools.certify issue --run results/runs/ws2_foreign --org "Acme Bank" \
        --agent "vendor-triage-v3 (gpt-4o)" --level self-tested
    python -m tools.certify verify --cert results/certs/<id>.json

Stdlib + `cryptography`. The PRIVATE key is gitignored; the PUBLIC key is committed
as the canonical verification key.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)

from common.claims import SELF_CERT_DISCLAIMER
from common.config import resolve

KEYS_DIR = resolve("tools", "keys")
PRIV_PATH = KEYS_DIR / "signing_private.hex"   # gitignored
PUB_PATH = KEYS_DIR / "signing_public.hex"     # committed = published verification key


def _canonical(obj: dict) -> bytes:
    """Deterministic JSON for signing/verifying (sorted keys, no whitespace)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def keygen() -> None:
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    priv = Ed25519PrivateKey.generate()
    priv_bytes = priv.private_bytes_raw()
    pub_bytes = priv.public_key().public_bytes_raw()
    PRIV_PATH.write_text(priv_bytes.hex())
    PUB_PATH.write_text(pub_bytes.hex())
    print(f"[certify] wrote private key -> {PRIV_PATH} (KEEP SECRET; gitignored)")
    print(f"[certify] wrote public  key -> {PUB_PATH} (publish/commit this)")


def _load_priv() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(PRIV_PATH.read_text().strip()))


def _battery_hash(cfg_output: str = "data/alerts.jsonl") -> str:
    p = resolve(cfg_output)
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()[:16] if p.exists() else "unknown"


def build_manifest(run_dir: Path, org: str, agent: str, level: str,
                   issued_at: str, valid_days: int) -> dict:
    """The certified payload: the substantive, anonymized metrics + provenance."""
    beh = json.loads((run_dir / "behavioral.json").read_text())
    val = json.loads((run_dir / "validation.json").read_text())
    ov = beh["overall"]
    exp = (datetime.fromisoformat(issued_at) + timedelta(days=valid_days)).isoformat()
    return {
        "schema": "cupel/self-cert/v1",
        "org": org,
        "agent_descriptor": agent,
        "assurance_level": level,   # self-tested | independent (paid)
        "battery_version": _battery_hash(),
        "metrics": {
            "under_escalation_neutral": ov["neutral_rate"],
            "under_escalation_incentivized": ov["incentivized_rate"],
            "susceptibility_delta": round(ov["incentivized_rate"] - ov["neutral_rate"], 4),
            "evaluator_vs_truth_agreement": val["defensible_vs_truth_agreement"],
            "under_escalation_detection_recall": val.get("suppression_detection", {}).get("recall"),
        },
        "issued_at": issued_at,
        "expires_at": exp,
        "disclaimer": SELF_CERT_DISCLAIMER,
    }


def issue(run_dir: Path, org: str, agent: str, level: str) -> dict:
    issued_at = datetime.now(timezone.utc).isoformat()
    manifest = build_manifest(run_dir, org, agent, level, issued_at, valid_days=90)
    priv = _load_priv()
    sig = priv.sign(_canonical(manifest)).hex()
    pub_hex = PUB_PATH.read_text().strip()
    cert_id = hashlib.sha256((_canonical(manifest) + sig.encode())).hexdigest()[:16]
    cert = {"cert_id": cert_id, "alg": "Ed25519", "manifest": manifest,
            "signature": sig, "public_key_hex": pub_hex}
    out = resolve("results", "certs", f"{cert_id}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cert, indent=2))
    print(f"[certify] issued cert {cert_id} -> {out}")
    return cert


def verify(cert: dict, trusted_pub_hex: str | None = None) -> tuple[bool, str]:
    """Verify a certificate against the PUBLISHED public key (key-pinned)."""
    trusted = trusted_pub_hex or (PUB_PATH.read_text().strip() if PUB_PATH.exists() else None)
    if trusted is None:
        return False, "no trusted public key available"
    if cert.get("public_key_hex") != trusted:
        return False, "public key mismatch (cert not signed by the trusted/published key)"
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(trusted))
        pub.verify(bytes.fromhex(cert["signature"]), _canonical(cert["manifest"]))
        return True, "valid: signature authentic and manifest unaltered"
    except Exception as e:
        return False, f"invalid signature / tampered manifest ({type(e).__name__})"


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("keygen")
    pi = sub.add_parser("issue")
    pi.add_argument("--run", required=True, help="run dir with behavioral.json + validation.json")
    pi.add_argument("--org", required=True)
    pi.add_argument("--agent", required=True)
    pi.add_argument("--level", default="self-tested", choices=["self-tested", "independent"])
    pv = sub.add_parser("verify")
    pv.add_argument("--cert", required=True)
    args = ap.parse_args()

    if args.cmd == "keygen":
        keygen()
    elif args.cmd == "issue":
        issue(resolve(args.run), args.org, args.agent, args.level)
    elif args.cmd == "verify":
        cert = json.loads(Path(args.cert).read_text())
        ok, reason = verify(cert)
        print(f"[certify] cert {cert.get('cert_id')}: {'✓' if ok else '✗'} {reason}")


if __name__ == "__main__":
    main()
