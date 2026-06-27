# Open-Core Self-Certification — Design

_An open-source synthetic-battery harness that lets companies self-test their
agents and obtain a cryptographically verifiable certificate, with paid independent
assurance as the higher trust tier. The free tier drives adoption and seeds the
corpus; the paid tier closes the gap the free tier structurally cannot._

---

## The trust ladder

| Tier | Who runs it | Data shared | What the badge means |
|---|---|---|---|
| **0. Practice** | Anyone (open repo + public battery) | none | dev/test only — no certificate |
| **1. Self-tested** (free/low-cost) | Company, against a **server-issued hidden challenge** | anonymized results only | "scored by us on a challenge they couldn't pre-train to; certificate authentic" |
| **2. Independent** (paid) | **Us**, against the company's live/sandboxed agent | per the data contract | "we drove their real agent end-to-end" |

Regulators already distinguish self-assessment from independent audit, so the tiers
map onto an accepted mental model.

## What cryptography can and cannot buy (be honest)

- **Can:** prove a certificate is **authentic** (signed by us) and **unaltered**
  (tamper-evident), and — with server-side scoring — that the **metrics were computed
  by us on a challenge the holder could not game**.
- **Cannot:** prove the holder pointed the harness at their **real production agent**
  rather than a nicer stand-in, or that their environment was honest. No purely
  cryptographic scheme closes this — the company controls the agent-under-test.
- **Therefore:** Tier 1 is *verifiable self-attestation*, not independent assurance.
  That residual gap **is** the paid product (Tier 2). The limitation is the business
  model, not a defect.

## Mechanism (Tier 1)

1. **Open repo** ships the harness + a **public *practice* battery** (so anyone can
   develop against it).
2. **Certification draws a fresh challenge** from a server-held, **rotating** battery
   with **private labels** (public/private split prevents train-to-the-benchmark).
   The harness fetches `{challenge_id, alerts (no labels), nonce}`.
3. Company runs its agent locally, submits `{challenge_id, nonce, decisions,
   rationales, anonymized agent_descriptor}`.
4. **Server scores against held-out labels** (the same `eval/metrics.py` +
   `evaluator/validate.py`) and **signs a certificate** over a canonical manifest.
5. **The "cryptographic indicator" = the Ed25519 signature.** Anyone verifies it
   against the published public key; a **public registry** lists issued certs.
   Anti-replay/freshness via `nonce` + `expires_at` + rotating `challenge_id`.

## Prototype in this repo (`tools/certify.py`)

Implements the signing primitive (server-side scoring is stubbed by reading an
existing run dir):

- `keygen` — Ed25519 keypair. **Private key gitignored**; `tools/keys/signing_public.hex`
  is committed as the canonical **published verification key**.
- `issue --run <dir> --org --agent --level` — builds the manifest (anonymized metrics
  + `battery_version` hash + issue/expiry + disclaimer) and signs it. Demonstrated
  over the WS2 foreign-agent metrics; see `results/certs/`.
- `verify --cert <file>` — **key-pinned** verification: rejects a key mismatch, an
  altered manifest, or a bad signature. Tamper-tested (flipping one metric →
  `InvalidSignature`).

Manifest is signed via **canonical JSON** (sorted keys, no whitespace) so signing and
verification are deterministic. Cert face carries an explicit `assurance_level` and a
`disclaimer` ("self-tested … NOT an independent audit") so a Tier-1 badge cannot be
passed off as Tier-2.

## Still to build for production Tier 1

- **Challenge-issuance + scoring service** (the only real infra): rotating private
  battery, nonce tracking, server-side scoring, registry. Start as a minimal API.
  **Designed in [`CHALLENGE_PROTOCOL.md`](CHALLENGE_PROTOCOL.md)** as the front half of
  the attestation mechanism; the seam (`battery.kind`/`battery.version`/`assurance_level`
  in `cert_request.json`) and a stub (`tools/challenge.py`) are in place.
- **Battery refresh cadence** + versioning policy (anti-staleness / anti-overfitting).
- **Key management** (rotation, an `expires_at` on the signing key, revocation list).
- **Registry + public verifier page** (paste a cert → validity + tier).

## Risks & mitigations

- **Train-to-the-benchmark** → rotating private challenge + periodic battery refresh.
- **Badge misrepresentation** (self-cert shown as audit) → explicit tier + disclaimer
  on the cert; registry shows tier; trademark the audited mark.
- **Liability of issuing a badge** → narrow, factual claims ("self-tested on synthetic
  battery vX on <date>"); no fitness/guarantee language.
- **Gaming the agent-under-test** → acknowledged; the explicit reason Tier 2 exists.

## Why this is strategically strong

The free tier removes the data-sharing barrier (nothing sensitive leaves), seeds a
public registry and an anonymized **results corpus** (the data moat behind the
benchmark and the paid services), and establishes us as the standard-setter — while
the honest limits of self-cert create the natural pull toward paid independent
assurance.
