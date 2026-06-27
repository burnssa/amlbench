"""Re-render a completed run's artifacts from saved data — NO model calls, $0.

Recomputes behavioral metrics (from decisions.jsonl), evaluator validation (from
verifications.jsonl), and the observability verdict/drift (from quality.jsonl if
present, else from the stored aggregates in observability.json), then re-renders
the ledger, assurance summary, attestation finding, plots, and REPORT.md.

    uv run python rerender.py --mode core
"""
from __future__ import annotations

import argparse

from common.config import load_config, resolve
from common.io import read_jsonl, read_json, write_json
from common import report as report_mod
from data import amlsim, build as databuild
from observability import metrics as obs_metrics
from eval import metrics as beh_metrics
from evaluator.validate import validate, readability_sample
from ledger.render import render_ledger, render_assurance_summary
from finding.attestation import build_finding, save_finding


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="core")
    args = ap.parse_args()
    cfg = load_config()
    run_dir = resolve("results", "runs", args.mode)

    decisions = list(read_jsonl(run_dir / "decisions.jsonl"))
    records = list(read_jsonl(run_dir / "verifications.jsonl"))
    neutral = [d for d in decisions if d["condition"] == "neutral"]
    incent = [d for d in decisions if d["condition"] == "incentivized"]

    behavioral = beh_metrics.full_report(neutral, incent)
    write_json(run_dir / "behavioral.json", behavioral)

    # Observability: prefer raw quality scores; else rebuild verdict/drift from the
    # aggregates already stored in observability.json.
    qpath = run_dir / "quality.jsonl"
    old = read_json(run_dir / "observability.json")
    if qpath.exists():
        q = list(read_jsonl(qpath))
        nq = [x for x in q if x.get("_cell") == "neutral"]
        iq = [x for x in q if x.get("_cell") == "incent"]
        core_seed, core_ph = cfg["run"]["core_seed"], cfg["run"]["core_phrasing"]
        on = [d for d in neutral if d["seed"] == core_seed] or neutral
        oi = [d for d in incent if d["seed"] == core_seed and d["phrasing"] == core_ph] or incent
        observability = obs_metrics.build_observability_report(on, nq, oi, iq, old.get("mode", "phoenix"))
    else:
        n_agg, i_agg = old["neutral"], old["incentivized"]
        d = old.get("drift", {})
        # Accept both the original run format and the re-rendered format.
        coh = old.get("quality_coherence_psi", d.get("coherence_score_psi"))
        length = old.get("output_length_psi_informational", d.get("output_length_psi"))
        observability = {
            "mode": old.get("mode", "phoenix"), "neutral": n_agg, "incentivized": i_agg,
            "verdict": obs_metrics.verdict(n_agg, i_agg),
            "drift": obs_metrics.drift_summary(
                float("nan") if coh is None else coh,
                float("nan") if length is None else length),
        }
    write_json(run_dir / "observability.json", observability)

    validation = validate(records)
    validation["readability_sample"] = readability_sample(records, cfg["evaluator_validation"]["readability_sample"])
    write_json(run_dir / "validation.json", validation)

    # dataset_summary (offline, deterministic, free)
    sub = amlsim.generate_substrate(cfg, cfg["run"]["core_seed"])
    dataset_summary = databuild.summarize(databuild.build_alerts(cfg, sub))

    # The WS2 foreign run writes a separate set of deliverables and must NOT clobber
    # the core report/ledger/plots. (Same $0 path; only the output targets differ.)
    is_foreign = args.mode == "ws2_foreign"
    if is_foreign:
        agent_model = decisions[0].get("agent_model", cfg["agent"]["model"])
        run_meta = {"mode": f"ws2_foreign:{agent_model}", "agent": agent_model,
                    "agent_descriptor": "cross-provider stand-in, vendor-style prompt",
                    "seeds": [cfg["run"]["core_seed"]],
                    "phrasings": [cfg["run"]["core_phrasing"]], "limit": len(neutral)}
        ledger_md = "results/ledger/foreign_decision_ledger.md"
        summary_md = "results/ledger/foreign_assurance_summary.md"
        finding_json, finding_md = "results/finding/foreign_attestation.json", "results/finding/foreign_attestation.md"
        report_path = "results/WS2_FOREIGN_REPORT.md"
    else:
        run_meta = {"mode": args.mode, "agent": cfg["agent"]["model"],
                    "seeds": [cfg["run"]["core_seed"]],
                    "phrasings": [cfg["run"]["core_phrasing"]], "limit": None}
        ledger_md = "results/ledger/decision_ledger.md"
        summary_md = "results/ledger/assurance_summary.md"
        finding_json, finding_md = "results/finding/attestation.json", "results/finding/attestation.md"
        report_path = cfg["reporting"]["report_path"]

    render_ledger(records, ledger_md)
    render_assurance_summary(records, behavioral, observability, validation, summary_md)
    finding = build_finding(behavioral, observability, validation, records, run_meta)
    save_finding(finding, finding_json, finding_md)

    from common.llm import _route
    from finding.cert_request import write_cert_request
    _ov = behavioral["overall"]
    _agent_id = run_meta.get("agent") or cfg["agent"]["model"]
    write_cert_request(
        cfg=cfg, run_meta=run_meta, conditions=["neutral", "incentivized"],
        provider=_route(_agent_id)[0], n_decisions=len(decisions),
        n_reportable=_ov["incentivized_total"], neutral_rate=_ov["neutral_rate"],
        incent_rate=_ov["incentivized_rate"], agreement=validation["defensible_vs_truth_agreement"],
        detection_recall=validation.get("suppression_detection", {}).get("recall"),
        out_path=("results/finding/foreign_cert_request.json" if is_foreign
                  else "results/finding/cert_request.json"),
        print_inline=False)
    # The WS2 report embeds no plots (matches ws2_milestone.py); re-rendering core
    # plots from foreign data would overwrite the core plots, so skip them there.
    if is_foreign:
        plot_paths = {}
    else:
        plot_paths = {
            "behavioral": report_mod.plot_behavioral(behavioral, cfg["reporting"]["plots_dir"]),
            "observability": report_mod.plot_observability(observability, cfg["reporting"]["plots_dir"]),
            "fidelity": report_mod.plot_fidelity(validation, cfg["reporting"]["plots_dir"]),
        }
    report_md = report_mod.build_report(
        cfg=cfg, run_meta=run_meta, dataset_summary=dataset_summary, behavioral=behavioral,
        observability=observability, validation=validation, records=records,
        plot_paths=plot_paths, finding=finding)
    resolve(report_path).write_text(report_md)

    v = observability["verdict"]
    print(f"[rerender] {args.mode}: under-esc "
          f"{behavioral['overall']['neutral_rate']:.1%}->{behavioral['overall']['incentivized_rate']:.1%} | "
          f"obs alarms {v['n_alarms']} (flags_failure={v['stack_flags_failure']}) | "
          f"drift_detected={observability['drift']['drift_detected']} | "
          f"agreement {validation['defensible_vs_truth_agreement']:.1%} | "
          f"induced-failure recall {validation['induced_failure_detection']['recall_via_either']}")


if __name__ == "__main__":
    main()
