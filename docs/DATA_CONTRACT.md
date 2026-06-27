# Data Contract & Privacy — what we need, and what we never want

_For prospect security / privacy review. The guiding principle: **you can't leak
what you never receive.** Most engagements need no sensitive data at all; when real
decisions are verified, only de-identified structured features are shared, produced
by a tool you run on your side._

---

## Engagement modes by data sensitivity (least-data first)

| Mode | What you provide | Sensitive data shared |
|---|---|---|
| **1. Synthetic battery** | An endpoint/sandbox of your agent (or run our battery yourself). We exercise it on *our* synthetic, ground-truth-labeled alerts. | **None.** No customer records involved at all. |
| **2. In-environment execution** | You run our harness (container) inside your VPC/on-prem. | **None leaves your environment.** Only aggregate metrics + a de-identified ledger come out. |
| **3. De-identified log-replay** | A sample of historical decisions, **de-identified by the tool below before it leaves your environment**. | De-identified structured features only — no PII. |

We recommend starting at Mode 1 (a no-data diagnostic) and graduating only as needed.

## The minimal data contract (Mode 3)

Per decision/alert, we need only what is required to (a) reconstruct the alert's
material features, (b) see the agent's decision and stated reasoning, and (c) derive
ground truth via deterministic BSA/AML rules. Concretely:

**Required**
- `alert_id` — any identifier (will be **tokenized** to a salted hash; the salt stays on your side).
- `decision` — `CLEAR` or `ESCALATE` (the agent's disposition).

**Recommended features (structured, non-PII) — as many as available**
- `window_days`, `n_transactions`, `total_inflow`, `total_outflow`, `max_amount`
- cash deposit amounts (list) or `n_cash_in`
- `passthrough_hours`, `passthrough_amount`
- `fanout_beneficiaries`, `fanout_total`
- `counterparty_country` (ISO-2 country code — not PII)
- `consistent_with_profile` (boolean)
- transaction ledger: `[{date, type, amount, direction}]` — **amounts/types/dates only, no account identifiers**

**Optional**
- `rationale`, `reasoning` — the agent's free-text justification (will be **PII-scrubbed** by the tool).

**Ground truth is derived on our side** by applying deterministic rules to the
features — you do **not** need to send labels (though you may supply your own
confirmed disposition if you want it used instead).

## What we never want — do not send (the tool blocks these)

Customer or counterparty **names**, **account / card numbers**, **SSNs/TINs**,
**addresses**, **emails**, **phone numbers**, **dates of birth**, IP/device
identifiers, raw KYC documents, or any free-text containing the above. The agent's
raw customer-facing narrative is **not** needed — we regenerate a neutral narrative
from the structured features.

## Privacy guarantees

- **Client-side de-identification** (`tools/desensitize.py`): runs entirely in your
  environment; raw data never moves. Identifiers are tokenized with a salt you keep;
  free-text is PII-scrubbed; the alert narrative is regenerated from features.
- **Automated leak-check**: the tool scans every output value for residual PII
  patterns (emails, phone, SSN, long digit runs) and **refuses to write** if any
  remain — so a malformed mapping fails closed, not open.
- **Zero retention**: under the DPA, de-identified inputs are deleted at the end of
  the engagement; nothing is retained without written consent.
- **No data at all in Modes 1–2**: the synthetic-battery and in-environment options
  require no customer records to leave your control.
