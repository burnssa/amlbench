# Held-out challenge set & attestation — protocol

> **Design doc + stub.** The challenge set is the un-gameable
> tier of the trust ladder and the **front half of paid independent attestation** — one
> mechanism, not two features. The set itself is server-held and never enters this repo.

## Why the challenge tier inverts the LogReplay flow

Self-certification on the **open practice battery** is gameable for one structural reason:
the practice battery ships to the user (`data.build --export-battery`), so they hold the
alerts and could pre-train to them. That is acceptable — practice is explicitly the weak,
"self-scored" tier (`battery.kind: open-practice`, `assurance_level: self-tested`).

A set you **cannot game** therefore **cannot be exported**. The user can never hold the
alerts or the labels. So the challenge tier cannot run
`--export-battery → run locally → --agent logreplay`. It must **invert**:

```
practice (gameable):   Cupel → export alerts → USER runs locally → USER returns CSV → score
challenge (un-gameable):           Cupel holds alerts → drives USER endpoint → Cupel scores server-side
```

The user's agent answers each alert through the black-box endpoint, but **never sees
ground truth and never keeps the set**.

## One mechanism: challenge == front half of attestation

The inverted flow is *almost exactly* the paid independent attestation flow:

| | Who drives | Alerts | Scoring | Trust |
|---|---|---|---|---|
| **Practice** (self-tested) | user, locally | exported, user holds | local | weak — gameable |
| **Challenge** (self-tested-challenge) | Cupel, self-serve | server-held | server-side | strong — un-gameable set |
| **Attestation** (independent) | Cupel, white-glove | server-held | server-side | strongest — Cupel drove the real agent |

Challenge and attestation share the same machinery — **Cupel holds the alerts, drives the
customer's endpoint, scores server-side.** They differ only in delivery (self-serve vs.
white-glove) and in what the certificate can claim. So this is not a separate build from
the attestation offering; **the held-out path is the attestation path**. Designing it once
also resolves the "how is it hidden if the user runs it?" tension before it can become a
contradiction in the copy: the user runs their *agent*, not the *set*.

## Protocol (single design for challenge + attestation)

1. **Cupel-side alert store (never published).** Rotated, versioned challenge sets with
   private labels. Never committed to this repo; `.gitignore` and `data.build` keep the
   repo shipping only the open practice battery.
2. **Endpoint contract** — the black-box `--agent api` contract already specified in
   `agent/byo.py` / `docs/BYO_GUIDE.md`: Cupel POSTs `{alert_id, alert, condition}`, the
   customer's endpoint returns `{decision, rationale}`. The customer exposes the endpoint;
   they never receive the set as a file.
3. **Server-side scoring** — the same `eval/metrics.py` + `evaluator/validate.py` the local
   path uses, run on Cupel's side against the held-out labels. Anti-replay/freshness via a
   per-challenge nonce + rotating `challenge_version`.
4. **Certificate** — signed over `cert_request.json` (`tools/certify.py`), with:
   - `battery.kind: held-out-challenge`
   - `battery.version: challenge-v<N>` (the rotated set id)
   - `battery.hash` pinning the exact set content
   - `assurance_level: self-tested-challenge`
   A cert against `challenge-v3` must not read identically to one against `challenge-v7`;
   both `version` and `hash` carry that.

## The seam already in the code

The fields that distinguish the tiers exist and are populated today
(`finding/cert_request.py`): `battery.kind`, `battery.version`, `assurance_level`. Step 6
wires the **held-out branch behind that seam** and **stubs the server-side load/score**
(`tools/challenge.py`, which raises `ChallengeUnavailable` in the open-source repo and
points here). The hosted Cupel service implements load + score.

## What ships where

| Artifact | Open-source repo | Hosted Cupel service |
|---|---|---|
| Open practice battery (`data/alerts.jsonl`, labeled `open-practice`) | ✅ committed | ✅ |
| Challenge alert store + private labels | ❌ never | ✅ server-only |
| `--export-battery` | ✅ (practice only) | n/a |
| Server-side challenge scoring | ❌ stub (`tools/challenge.py`) | ✅ |
| Cert signing/verify (`tools/certify.py`) | ✅ | ✅ |

## Ship-time sync (page-matches-code discipline)

When the real challenge path ships, **two things flip together**:
1. the cert's `assurance_level` → `self-tested-challenge` (and `battery.kind` →
   `held-out-challenge`, `battery.version` → the set id), and
2. the landing-page cert tier copy → from *"self-scored on the open practice battery"* to
   the un-gameable claim.

Neither moves without the other. Until then, all real runs emit `open-practice` and the
copy stays scoped to "self-scored on the open practice battery."

## Risks (carried from the self-cert design)

- **Train-to-the-benchmark** → the set is never exported + rotated/versioned.
- **Badge misrepresentation** (challenge shown as attestation) → distinct `assurance_level`;
  attestation requires Cupel to have driven the *real* production agent, which the
  challenge tier cannot prove (the customer still controls which agent answers the endpoint).
- **Stale set** → rotation cadence + `battery.version` in every cert.
