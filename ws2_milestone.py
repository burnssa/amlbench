"""WS2 de-risking milestone: run the COMPLETE assurance pipeline against a
cross-provider stand-in agent (GPT-4o behind a vendor-style prompt, via the
BYO-agent adapter), on the shared 84-alert battery. Proves the pipeline can drive
a customer's agent end-to-end through the adapter and emit the sellable deliverables.

    uv run python ws2_milestone.py            # ~$20 (Opus evaluator is the driver)
    uv run python ws2_milestone.py --model gpt-4o --clears 24

Outputs (kept separate from the core run so nothing is clobbered):
  results/runs/ws2_foreign/{decisions,quality,verifications}.jsonl + *.json
  results/ledger/foreign_{decision_ledger,assurance_summary}.md
  results/finding/foreign_attestation.{json,md}
  results/WS2_FOREIGN_REPORT.md
"""
from __future__ import annotations

import argparse

from common.config import load_config, resolve
from common.io import read_jsonl, write_json, write_jsonl
from common.llm import api_key_available
from common.parallel import thread_map
from common import report as report_mod
from agent.adapter import ForeignVendorAgent
from data import build as databuild
from eval.probe import build_probe_set
from eval import metrics as beh_metrics
from observability import instrument, metrics as obs_metrics
from evaluator.verify import verify_decisions
from evaluator.validate import validate, readability_sample
from ledger.render import render_ledger, render_assurance_summary
from finding.attestation import build_finding, evidence_locations, save_finding


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gpt-4o", help="foreign agent model id")
    ap.add_argument("--clears", type=int, default=24)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    cfg = load_config()
    if not api_key_available():
        raise SystemExit("ANTHROPIC_API_KEY not set (evaluator/quality need it).")
    seed = cfg["run"]["core_seed"]
    core_ph = cfg["run"]["core_phrasing"]

    alerts = list(read_jsonl(resolve(cfg["dataset"]["output"])))
    battery = build_probe_set(alerts, args.clears, seed)
    agent = ForeignVendorAgent(args.model, cfg)
    print(f"[ws2] foreign agent '{args.model}' (vendor-style prompt) on {len(battery)} alerts; "
          f"neutral vs '{core_ph}'")

    # ── run the foreign agent through both conditions ──────────────────────
    cells = [("neutral", None), ("incentivized", core_ph)]
    decisions = []
    for condition, phrasing in cells:
        decs = thread_map(lambda a: agent.triage(a, condition, phrasing), battery,
                          workers=args.workers, label=f"foreign {condition}/{phrasing or '-'}")
        decisions += [d for d in decs if d]

    run_dir = resolve("results", "runs", "ws2_foreign")
    write_jsonl(run_dir / "decisions.jsonl", decisions)
    parse_ok = sum(d["parse_ok"] for d in decisions)
    print(f"  [ws2] {len(decisions)} decisions, parse_ok {parse_ok}/{len(decisions)}")
    neutral = [d for d in decisions if d["condition"] == "neutral"]
    incent = [d for d in decisions if d["condition"] == "incentivized"]

    # ── Pillar A observability (gap holds on the foreign agent too) ─────────
    mode = instrument.init_phoenix(cfg)
    for d in decisions:
        instrument.trace_decision(d)
    nq = thread_map(lambda d: instrument.score_quality(d, cfg), neutral, workers=args.workers, label="quality-neu")
    iq = thread_map(lambda d: instrument.score_quality(d, cfg), incent, workers=args.workers, label="quality-inc")
    observability = obs_metrics.build_observability_report(neutral, nq, incent, iq, mode)
    write_json(run_dir / "observability.json", observability)
    write_jsonl(run_dir / "quality.jsonl",
                [{**q, "_cell": "neutral"} for q in nq] + [{**q, "_cell": "incent"} for q in iq])

    # ── Pillar A behavioral + Pillar B verification ────────────────────────
    behavioral = beh_metrics.full_report(neutral, incent)
    write_json(run_dir / "behavioral.json", behavioral)
    print(f"  [ws2] verifying {len(decisions)} foreign-agent decisions with {cfg['evaluator']['model']}…")
    records = [r for r in verify_decisions(decisions, cfg) if r]
    write_jsonl(run_dir / "verifications.jsonl", records)
    validation = validate(records)
    validation["readability_sample"] = readability_sample(records, cfg["evaluator_validation"]["readability_sample"])
    write_json(run_dir / "validation.json", validation)

    # ── foreign-agent deliverables ─────────────────────────────────────────
    run_meta = {"mode": f"ws2_foreign:{args.model}", "agent": args.model,
                "agent_descriptor": "cross-provider stand-in, vendor-style prompt",
                "seeds": [seed], "phrasings": [core_ph], "limit": len(battery)}
    render_ledger(records, "results/ledger/foreign_decision_ledger.md")
    render_assurance_summary(records, behavioral, observability, validation,
                             "results/ledger/foreign_assurance_summary.md")
    finding = build_finding(behavioral, observability, validation, records, run_meta,
                            evidence_paths=evidence_locations(
                                "results/ledger/foreign_decision_ledger.md",
                                "results/ledger/foreign_assurance_summary.md",
                                "results/runs/ws2_foreign"))
    save_finding(finding, "results/finding/foreign_attestation.json", "results/finding/foreign_attestation.md")
    from common.llm import _route
    from finding.cert_request import write_cert_request
    _ov = behavioral["overall"]
    write_cert_request(
        cfg=cfg, run_meta=run_meta, conditions=["neutral", "incentivized"],
        provider=_route(args.model)[0], n_decisions=len(decisions),
        n_reportable=_ov["incentivized_total"], neutral_rate=_ov["neutral_rate"],
        incent_rate=_ov["incentivized_rate"], agreement=validation["defensible_vs_truth_agreement"],
        detection_recall=validation.get("suppression_detection", {}).get("recall"),
        out_path="results/finding/foreign_cert_request.json")
    dataset_summary = databuild.summarize(battery)
    report_md = report_mod.build_report(
        cfg=cfg, run_meta=run_meta, dataset_summary=dataset_summary, behavioral=behavioral,
        observability=observability, validation=validation, records=records, plot_paths={}, finding=finding)
    resolve("results", "WS2_FOREIGN_REPORT.md").write_text(report_md)

    ov = behavioral["overall"]
    v = observability["verdict"]
    cost = (sum(d["usage"]["cost_usd"] for d in decisions)
            + sum(q.get("judge_cost_usd", 0) for q in nq + iq)
            + sum(r.get("evaluator_cost_usd", 0) for r in records))
    print("\n" + "=" * 70)
    print(f"WS2 FOREIGN-AGENT MILESTONE — agent '{args.model}' (not authored by us)")
    print(f"  under-escalation {ov['neutral_rate']:.1%} -> {ov['incentivized_rate']:.1%} "
          f"(h={ov['cohens_h']}, p={ov['p_value']})")
    print(f"  observability alarms: {v['n_alarms']} (flags_failure={v['stack_flags_failure']})")
    print(f"  evaluator-vs-truth agreement: {validation['defensible_vs_truth_agreement']:.1%}; "
          f"under-escalation detection recall: {validation['suppression_detection']['recall']}")
    print(f"  est. spend: ${cost:.2f}")
    print(f"  deliverables: results/ledger/foreign_*.md, results/finding/foreign_attestation.*,")
    print(f"                results/WS2_FOREIGN_REPORT.md")
    print("=" * 70)


if __name__ == "__main__":
    main()
