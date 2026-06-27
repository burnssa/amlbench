"""The AML triage agent: alert -> explicit reasoning -> CLEAR/ESCALATE + rationale.

The exposed `reasoning` and `rationale` are exactly what the Pillar-B evaluator
inspects. Token usage and latency are captured on every call so the Pillar-A
observability arm can compute cost/latency/throughput with no extra hooks.
"""
from __future__ import annotations

import argparse

from common.config import load_config, resolve
from common.io import read_jsonl, write_jsonl
from common.llm import complete, extract_json
from agent.conditions import system_prompt

# Feature keys shown to the agent. We deliberately exclude the ground-truth block.
_SHOWN_FEATURES = [
    ("n_transactions", "transactions in window"),
    ("window_days", "window length (days)"),
    ("total_inflow", "total inflow (USD)"),
    ("total_outflow", "total outflow (USD)"),
    ("max_amount", "largest single transaction (USD)"),
    ("n_cash_in", "number of cash deposits"),
    ("passthrough_hours", "in/out pass-through gap (hours, null if none)"),
    ("passthrough_amount", "pass-through amount (USD)"),
    ("fanout_beneficiaries", "distinct outgoing beneficiaries"),
    ("fanout_total", "total dispersed (USD)"),
    ("counterparty_country", "predominant counterparty country"),
    ("watchlist_hit", "sanctions/watchlist hit"),
    ("consistent_with_profile", "consistent with customer profile"),
]


def present_alert(alert: dict) -> str:
    f = alert["features"]
    lines = [alert["narrative"], "", "Structured indicators:"]
    for key, desc in _SHOWN_FEATURES:
        lines.append(f"  - {desc}: {f.get(key)}")
    # For subtle alerts the deposits live in the ledger inside the narrative — we do
    # NOT pre-extract them here, so the agent must spot the pattern itself.
    if f.get("cash_transactions") and not alert.get("subtle"):
        amts = ", ".join(f"${c['amount']:,.0f}" for c in f["cash_transactions"])
        lines.append(f"  - individual cash deposit amounts: {amts}")
    lines.append("\nReturn your triage decision as the specified JSON object.")
    return "\n".join(lines)


def decide(alert: dict, *, system: str, model: str, condition: str, phrasing: str | None,
           seed: int, max_tokens: int, temperature: float) -> dict:
    """Core triage call: given any system prompt + model, produce a decision record.

    Model-agnostic (routes by model id) and agent-agnostic — the BYO-agent adapters
    (agent/adapter.py) drive this with the system-under-test's own prompt.
    """
    class _Empty:
        text = ""
        model_ = model
        input_tokens = output_tokens = 0
        latency_s = cost_usd = 0.0

    try:
        resp = complete(model=model, system=system, user=present_alert(alert),
                        max_tokens=max_tokens, temperature=temperature)
    except Exception as e:
        # API failure after retries: fail safe (escalate), don't abort the run.
        resp = _Empty()
        resp.text = f"__API_ERROR__: {e}"
        resp.model = model

    try:
        parsed = extract_json(resp.text)
        decision = str(parsed.get("decision", "")).upper().strip()
        if decision not in ("ESCALATE", "CLEAR"):
            decision = "ESCALATE"  # fail safe: an unparseable decision is treated as escalate
        reasoning = str(parsed.get("reasoning", ""))
        rationale = str(parsed.get("rationale", ""))
        parse_ok = True
    except Exception:
        decision, reasoning, rationale, parse_ok = "ESCALATE", resp.text, "", False

    return {
        "alert_id": alert["alert_id"],
        "condition": condition,
        "phrasing": phrasing,
        "seed": seed,
        "decision": decision,
        "rationale": rationale,
        "reasoning": reasoning,
        "parse_ok": parse_ok,
        "agent_model": resp.model,
        "usage": {
            "input_tokens": resp.input_tokens,
            "output_tokens": resp.output_tokens,
            "latency_s": round(resp.latency_s, 3),
            "cost_usd": round(resp.cost_usd, 6),
        },
        # Carried for downstream scoring; NOT shown to the agent or evaluator.
        "gt_label": alert["ground_truth"]["label"],
        "gt_typology": alert["gt_typology"],
        "narrative": alert["narrative"],
        "features": alert["features"],
        "subtle": alert.get("subtle", False),
    }


def triage_one(alert: dict, condition: str, phrasing: str | None, cfg: dict, seed: int) -> dict:
    """Reference agent: our triage prompt + the condition's incentive context."""
    return decide(
        alert, system=system_prompt(condition, phrasing, cfg), model=cfg["agent"]["model"],
        condition=condition, phrasing=phrasing, seed=seed,
        max_tokens=cfg["agent"]["max_tokens"], temperature=cfg["agent"]["temperature"],
    )


def run_condition(alerts: list[dict], condition: str, phrasing: str | None, cfg: dict, seed: int) -> list[dict]:
    from common.parallel import thread_map
    workers = cfg.dotget("run.workers", 8) if hasattr(cfg, "dotget") else 8
    return thread_map(
        lambda a: triage_one(a, condition, phrasing, cfg, seed),
        alerts, workers=workers, label=f"agent {condition}/{phrasing}",
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--condition", required=True, choices=["neutral", "incentivized"])
    ap.add_argument("--phrasing", default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    cfg = load_config()
    seed = args.seed if args.seed is not None else cfg["run"]["core_seed"]
    alerts = list(read_jsonl(resolve(cfg["dataset"]["output"])))
    if args.limit:
        alerts = alerts[: args.limit]
    rows = run_condition(alerts, args.condition, args.phrasing, cfg, seed)
    out = resolve("results", "runs", f"agent_{args.condition}_{args.phrasing or 'default'}_s{seed}.jsonl")
    write_jsonl(out, rows)
    n_esc = sum(1 for r in rows if r["decision"] == "ESCALATE")
    print(f"[agent] {args.condition}/{args.phrasing} seed={seed}: {len(rows)} decisions, "
          f"{n_esc} escalate -> {out}")


if __name__ == "__main__":
    main()
