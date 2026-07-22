"""Single documented command reproducing the core result, end-to-end.

    uv run python run.py --mode dry      # ~12 alerts, cheapest plumbing check (~$1)
    uv run python run.py --mode core     # full N, 1 seed/1 phrasing — the headline run
    uv run python run.py --mode full     # all seeds x all phrasings — robustness

Pipeline: dataset (AMLSim-derived) -> agent triage (neutral + incentivized)
       -> Pillar A observability arm (Phoenix) -> Pillar A behavioral arm
       -> Pillar B per-decision evaluator + validation
       -> decision ledger + assurance summary + attestation finding + REPORT.md
"""
from __future__ import annotations

import argparse
import random
import sys

from common.config import load_config, resolve
from common.io import write_json, write_jsonl
from common import report as report_mod
from common.llm import api_key_available
from data import amlsim, build as databuild
from agent.triage import run_condition
from agent.conditions import incentive_phrasings
from observability import instrument, metrics as obs_metrics
from eval import metrics as beh_metrics
from evaluator.verify import verify_decisions
from evaluator.validate import validate, readability_sample
from ledger.render import render_ledger, render_assurance_summary
from finding.attestation import build_finding, evidence_locations, save_finding

ESCALATE = "SHOULD_ESCALATE"


def stratified_sample(alerts: list[dict], limit: int, seed: int) -> list[dict]:
    """Keep a representative mix (structuring + other escalate + clears) when limiting."""
    rng = random.Random(seed)
    struct = [a for a in alerts if a["gt_typology"] == "structuring"]
    esc = [a for a in alerts if a["ground_truth"]["label"] == ESCALATE and a["gt_typology"] != "structuring"]
    clear = [a for a in alerts if a["ground_truth"]["label"] != ESCALATE]
    n_struct = max(2, limit // 4)
    n_esc = max(2, limit // 4)
    n_clear = limit - n_struct - n_esc
    pick = (rng.sample(struct, min(n_struct, len(struct)))
            + rng.sample(esc, min(n_esc, len(esc)))
            + rng.sample(clear, min(max(n_clear, 0), len(clear))))
    rng.shuffle(pick)
    return pick


def dataset_for_seed(cfg, seed, limit):
    sub = amlsim.generate_substrate(cfg, seed)
    alerts = databuild.build_alerts(cfg, sub)
    summary = databuild.summarize(alerts)
    if limit:
        alerts = stratified_sample(alerts, limit, seed)
        summary = databuild.summarize(alerts)
    return alerts, summary


def _byo_decisions(args, cfg, battery: dict) -> tuple[list[dict], str, str]:
    """Get decision records from the customer's agent (logreplay CSV or api endpoint)."""
    label = args.model or args.agent
    if args.agent == "logreplay":
        if not args.decisions:
            sys.exit("--agent logreplay requires --decisions <csv>")
        from agent.byo import load_logreplay_decisions
        from common.netguard import no_network
        from pathlib import Path
        # The whole ingest runs offline — proven, not promised.
        with no_network():
            decs = load_logreplay_decisions(args.decisions, battery, agent_label=label)
        return decs, f"logreplay:{Path(args.decisions).name}", label
    # api (BETA): black-box endpoint, as-is verification (single condition).
    if not args.endpoint:
        sys.exit("--agent api requires --endpoint <url>")
    from agent.byo import ApiAgent
    from common.parallel import thread_map
    print("[byo] api path is BETA — your endpoint is treated as a black box (as-is verification); "
          "no other host is contacted.")
    agent = ApiAgent(args.endpoint, label)
    alerts = list(battery.values())
    decs = thread_map(lambda a: agent.triage(a, "neutral", None), alerts,
                      workers=args.workers, label="byo api")
    return decs, f"api:{args.endpoint}", label


def run_byo(args, cfg) -> None:
    """Assurance pipeline against a CUSTOMER's agent. Emits the same deliverable shapes
    as the reference run, to BYO-namespaced paths. The under-escalation number is computed
    offline and printed first; the independent ledger/attestation (which send the decisions
    to the evaluator) run only if ANTHROPIC_API_KEY is set."""
    from collections import defaultdict
    from agent.byo import load_battery

    # Held-out challenge tier: server-side, never local. The set is not in this repo
    # (that is what makes it un-gameable) — see docs/CHALLENGE_PROTOCOL.md.
    if args.challenge:  # main() guarantees --agent api here; the set is server-side, never local
        from tools.challenge import ChallengeUnavailable, require_challenge
        try:
            require_challenge()
        except ChallengeUnavailable as e:
            sys.exit(f"[challenge] {e}")

    battery = load_battery(resolve(cfg["dataset"]["output"]))
    if not battery:
        sys.exit("No battery found. Run `uv run python -m data.build --export-battery` first.")

    decisions, src, label = _byo_decisions(args, cfg, battery)
    decisions = [d for d in decisions if d]
    if not decisions:
        sys.exit("[byo] no decisions to score.")

    out = args.out_root
    run_dir = resolve(out, "runs", "byo")
    write_jsonl(run_dir / "decisions.jsonl", decisions)
    by_cond: dict[str, list] = defaultdict(list)
    for d in decisions:
        by_cond[d["condition"]].append(d)
    print(f"[byo] {len(decisions)} decisions from {src}; conditions "
          f"{ {k: len(v) for k, v in by_cond.items()} }")
    # ── the hero number: under-escalation, offline, printed first ──────────
    for cond, ds in sorted(by_cond.items()):
        rate, missed, total = beh_metrics.under_escalation_rate(ds)
        print(f"  [byo] under-escalation ({cond}): {rate:.1%}  ({missed}/{total} reportable alerts cleared)")

    neutral = by_cond.get("neutral") or by_cond.get("as_is") or []
    incent = by_cond.get("incentivized") or []
    if not neutral and len(by_cond) == 1:
        neutral = next(iter(by_cond.values()))
    have_contrast = bool(neutral and incent)

    run_meta = {"mode": f"byo:{label}", "agent": label, "agent_descriptor": src,
                "seeds": [0], "phrasings": sorted(by_cond.keys()), "limit": len(decisions)}
    provider = "logreplay (offline)" if args.agent == "logreplay" else "customer-endpoint"
    _ne = beh_metrics.under_escalation_rate(neutral)
    _ie = beh_metrics.under_escalation_rate(incent) if incent else None

    def _emit_cert(validation=None):
        # A self-serve user who just scored their agent is exactly who wants a cert.
        from finding.cert_request import write_cert_request
        write_cert_request(
            cfg=cfg, run_meta=run_meta, conditions=sorted(by_cond.keys()), provider=provider,
            n_decisions=len(decisions), n_reportable=(_ie[2] if _ie else _ne[2]),
            neutral_rate=_ne[0], incent_rate=(_ie[0] if _ie else None),
            agreement=(validation or {}).get("defensible_vs_truth_agreement"),
            detection_recall=(validation or {}).get("suppression_detection", {}).get("recall"),
            out_path=f"{out}/finding/byo_cert_request.json")

    if not api_key_available():
        print(f"\n[byo] ANTHROPIC_API_KEY not set — delivered your under-escalation number above and\n"
              f"      {run_dir}/decisions.jsonl. Nothing left your machine this run. Set the key to\n"
              f"      also produce the independent ledger + attestation (that stage sends the\n"
              f"      decisions — not your raw data — to the evaluator).")
        _emit_cert()
        return

    # ── Pillar B: independent per-decision verification ────────────────────
    print(f"[byo] verifying {len(decisions)} decisions with {cfg['evaluator']['model']}…")
    records = [r for r in verify_decisions(decisions, cfg) if r]
    write_jsonl(run_dir / "verifications.jsonl", records)
    validation = validate(records)
    validation["readability_sample"] = readability_sample(records, cfg["evaluator_validation"]["readability_sample"])
    write_json(run_dir / "validation.json", validation)
    render_ledger(records, f"{out}/ledger/byo_decision_ledger.md")

    if not have_contrast:
        print("[byo] single-condition (as-is) run: emitted the independent ledger + validation.\n"
              "      A susceptibility REPORT needs both `neutral` and `incentivized` conditions.\n"
              f"      deliverables: {out}/ledger/byo_decision_ledger.md, {run_dir}/validation.json")
        _emit_cert(validation)
        return

    # ── contrast (susceptibility) path: full deliverables, mirroring reference ──
    from common.parallel import thread_map
    behavioral = beh_metrics.full_report(neutral, incent)
    write_json(run_dir / "behavioral.json", behavioral)
    mode = instrument.init_phoenix(cfg)
    for d in decisions:
        instrument.trace_decision(d)
    nq = thread_map(lambda d: instrument.score_quality(d, cfg), neutral, workers=args.workers, label="byo quality-neu")
    iq = thread_map(lambda d: instrument.score_quality(d, cfg), incent, workers=args.workers, label="byo quality-inc")
    observability = obs_metrics.build_observability_report(neutral, nq, incent, iq, mode)
    write_json(run_dir / "observability.json", observability)
    render_assurance_summary(records, behavioral, observability, validation,
                             f"{out}/ledger/byo_assurance_summary.md")
    finding = build_finding(behavioral, observability, validation, records, run_meta,
                            evidence_paths=evidence_locations(
                                f"{out}/ledger/byo_decision_ledger.md",
                                f"{out}/ledger/byo_assurance_summary.md",
                                f"{out}/runs/byo"))
    save_finding(finding, f"{out}/finding/byo_attestation.json", f"{out}/finding/byo_attestation.md")
    dataset_summary = databuild.summarize(list(battery.values()))
    report_md = report_mod.build_report(
        cfg=cfg, run_meta=run_meta, dataset_summary=dataset_summary, behavioral=behavioral,
        observability=observability, validation=validation, records=records, plot_paths={}, finding=finding)
    resolve(out, "BYO_REPORT.md").write_text(report_md)

    ov = behavioral["overall"]
    print("\n" + "=" * 70)
    print(f"BYO ASSURANCE — agent '{label}' ({src})")
    print(f"  under-escalation {ov['neutral_rate']:.1%} -> {ov['incentivized_rate']:.1%} "
          f"(h={ov['cohens_h']}, p={ov['p_value']})")
    print(f"  evaluator-vs-truth agreement: {validation['defensible_vs_truth_agreement']:.1%}")
    print(f"  deliverables: {out}/BYO_REPORT.md, {out}/ledger/byo_*.md, {out}/finding/byo_attestation.*")
    print("=" * 70)
    _emit_cert(validation)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["dry", "core", "full"], default="core")
    ap.add_argument("--limit", type=int, default=None, help="override alert count")
    # ── bring-your-own-agent (BYO) ─────────────────────────────────────────
    ap.add_argument("--agent", choices=["reference", "logreplay", "api"], default="reference",
                    help="reference=our agent; logreplay=score a decisions CSV; api=BETA black-box endpoint")
    ap.add_argument("--decisions", default=None, metavar="CSV",
                    help="[--agent logreplay] your agent's decisions on the exported battery")
    ap.add_argument("--endpoint", default=None, metavar="URL",
                    help="[--agent api] your agent's HTTP endpoint (black-box contract; see agent/byo.py)")
    ap.add_argument("--model", default=None, metavar="LABEL",
                    help="[BYO] descriptor for your agent, shown in the report/cert")
    ap.add_argument("--challenge", action="store_true",
                    help="[--agent api] held-out un-gameable tier (server-side; see docs/CHALLENGE_PROTOCOL.md)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out-root", default="results", metavar="DIR",
                    help="root for report/ledger/finding/plot deliverables. Smoke/CI runs pass "
                         "results/smoke (gitignored) so plumbing checks can never overwrite the "
                         "committed results/ artifacts.")
    args = ap.parse_args()

    cfg = load_config()
    if args.challenge and args.agent != "api":
        sys.exit("--challenge runs only via --agent api (the held-out challenge set drives your endpoint).")
    if args.agent != "reference":
        run_byo(args, cfg)
        return
    if not api_key_available():
        print("ERROR: ANTHROPIC_API_KEY not set. Put it in a .env file at the repo root "
              "(the offline data layer runs without it; the agent/evaluator/Phoenix evals need it).")
        sys.exit(1)

    if args.mode == "dry":
        seeds, phrasings, limit = [cfg["run"]["core_seed"]], [cfg["run"]["core_phrasing"]], (args.limit or 12)
    elif args.mode == "core":
        seeds, phrasings, limit = [cfg["run"]["core_seed"]], [cfg["run"]["core_phrasing"]], args.limit
    else:
        seeds, phrasings, limit = cfg["run"]["seeds"], incentive_phrasings(cfg), args.limit

    out = args.out_root
    run_dir = resolve(out, "runs", args.mode)
    run_meta = {"mode": args.mode, "agent": cfg["agent"]["model"], "seeds": seeds,
                "phrasings": phrasings, "limit": limit}
    print(f"[run] mode={args.mode} seeds={seeds} phrasings={phrasings} limit={limit}")

    # ── 1. dataset + 2. agent triage across cells ──────────────────────────
    all_decisions: list[dict] = []
    dataset_summary = None
    for seed in seeds:
        alerts, dataset_summary = dataset_for_seed(cfg, seed, limit)
        print(f"[data] seed={seed}: {dataset_summary['n_alerts']} alerts, "
              f"{dataset_summary['n_escalate']} escalate, {dataset_summary['n_structuring']} structuring")
        print(f"  [agent] neutral seed={seed} ({len(alerts)} alerts)…")
        all_decisions += run_condition(alerts, "neutral", None, cfg, seed)
        for ph in phrasings:
            print(f"  [agent] incentivized/{ph} seed={seed}…")
            all_decisions += run_condition(alerts, "incentivized", ph, cfg, seed)

    all_decisions = [d for d in all_decisions if d]  # drop any isolated failures
    write_jsonl(run_dir / "decisions.jsonl", all_decisions)
    neutral = [d for d in all_decisions if d["condition"] == "neutral"]
    incentivized = [d for d in all_decisions if d["condition"] == "incentivized"]

    # ── 3. Pillar A — observability arm (matched core cell) ────────────────
    mode = instrument.init_phoenix(cfg)
    core_seed, core_ph = cfg["run"]["core_seed"], cfg["run"]["core_phrasing"]
    obs_neutral = [d for d in neutral if d["seed"] == core_seed] or neutral
    obs_incent = ([d for d in incentivized if d["seed"] == core_seed and d["phrasing"] == core_ph]
                  or incentivized)
    print(f"[observability] scoring quality on {len(obs_neutral)}+{len(obs_incent)} decisions (mode={mode})…")
    for d in all_decisions:
        instrument.trace_decision(d)
    from common.parallel import thread_map
    w = cfg.dotget("run.workers", 8)
    nq = thread_map(lambda d: instrument.score_quality(d, cfg), obs_neutral, workers=w, label="quality-neutral")
    iq = thread_map(lambda d: instrument.score_quality(d, cfg), obs_incent, workers=w, label="quality-incent")
    observability = obs_metrics.build_observability_report(obs_neutral, nq, obs_incent, iq, mode)
    write_json(run_dir / "observability.json", observability)
    # Persist raw quality scores so the run can be re-rendered offline (no re-spend).
    write_jsonl(run_dir / "quality.jsonl",
                [{**q, "_cell": "neutral"} for q in nq] + [{**q, "_cell": "incent"} for q in iq])

    # ── 4. Pillar A — behavioral arm ───────────────────────────────────────
    behavioral = beh_metrics.full_report(neutral, incentivized)
    write_json(run_dir / "behavioral.json", behavioral)

    # ── 5. Pillar B — per-decision evaluator + validation ──────────────────
    print(f"[evaluator] verifying {len(all_decisions)} decisions with {cfg['evaluator']['model']}…")
    records = [r for r in verify_decisions(all_decisions, cfg) if r]
    write_jsonl(run_dir / "verifications.jsonl", records)
    validation = validate(records)
    validation["readability_sample"] = readability_sample(records, cfg["evaluator_validation"]["readability_sample"])
    write_json(run_dir / "validation.json", validation)

    # ── 6. product surfaces: ledger + assurance summary + finding + report ──
    render_ledger(records, f"{out}/ledger/decision_ledger.md")
    render_assurance_summary(records, behavioral, observability, validation,
                             f"{out}/ledger/assurance_summary.md")
    finding = build_finding(behavioral, observability, validation, records, run_meta,
                            evidence_paths=evidence_locations(
                                f"{out}/ledger/decision_ledger.md",
                                f"{out}/ledger/assurance_summary.md",
                                f"{out}/runs/{args.mode}"))
    save_finding(finding, f"{out}/finding/attestation.json", f"{out}/finding/attestation.md")

    # cert_request.json — anonymized, aggregate-only; printed inline at run's end.
    from common.llm import _route
    from finding.cert_request import write_cert_request
    _ov = behavioral["overall"]
    write_cert_request(
        cfg=cfg, run_meta=run_meta, conditions=["neutral", "incentivized"],
        provider=_route(cfg["agent"]["model"])[0], n_decisions=len(all_decisions),
        n_reportable=_ov["incentivized_total"], neutral_rate=_ov["neutral_rate"],
        incent_rate=_ov["incentivized_rate"], agreement=validation["defensible_vs_truth_agreement"],
        detection_recall=validation.get("suppression_detection", {}).get("recall"),
        out_path=f"{out}/finding/cert_request.json")

    # Default out-root keeps the cfg-specified locations; a custom root self-contains everything.
    plots_dir = cfg["reporting"]["plots_dir"] if out == "results" else f"{out}/plots"
    report_path = resolve(cfg["reporting"]["report_path"]) if out == "results" else resolve(out, "REPORT.md")
    plot_paths = {
        "behavioral": report_mod.plot_behavioral(behavioral, plots_dir),
        "observability": report_mod.plot_observability(observability, plots_dir),
        "fidelity": report_mod.plot_fidelity(validation, plots_dir),
    }
    report_md = report_mod.build_report(
        cfg=cfg, run_meta=run_meta, dataset_summary=dataset_summary, behavioral=behavioral,
        observability=observability, validation=validation, records=records,
        plot_paths=plot_paths, finding=finding)
    report_path.write_text(report_md)

    # ── console headline ───────────────────────────────────────────────────
    ov = behavioral["overall"]
    st = behavioral["per_typology"].get("structuring", {})
    total_cost = (sum(d["usage"]["cost_usd"] for d in all_decisions)
                  + sum(q.get("judge_cost_usd", 0) for q in nq + iq)
                  + sum(r.get("evaluator_cost_usd", 0) for r in records))
    print("\n" + "=" * 70)
    print(f"HEADLINE  under-escalation {ov['neutral_rate']:.1%} -> {ov['incentivized_rate']:.1%} "
          f"(h={ov['cohens_h']}, p={ov['p_value']})")
    if st:
        print(f"          structuring suppression {st['neutral_rate']:.1%} -> {st['incentivized_rate']:.1%}")
    print(f"          observability alarms: {observability['verdict']['n_alarms']} "
          f"(flags failure: {observability['verdict']['stack_flags_failure']})")
    print(f"          evaluator-vs-truth agreement: {validation['defensible_vs_truth_agreement']:.1%}; "
          f"induced-failure recall: {validation['induced_failure_detection']['recall_via_either']}")
    print(f"          est. spend this run: ${total_cost:.2f}")
    print(f"\nArtifacts: {report_path}")
    print(f"           {out}/ledger/{{decision_ledger,assurance_summary}}.md")
    print(f"           {out}/finding/attestation.{{json,md}}")
    print("=" * 70)


if __name__ == "__main__":
    main()
