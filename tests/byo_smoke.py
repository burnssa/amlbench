"""BYO offline end-to-end smoke: stubs the Anthropic client and runs the real
run.run_byo (logreplay contrast path) on the sample CSV, proving a BYO run emits the
same deliverable shapes as the reference run — REPORT + ledger + attestation — with no
network or cost.

    uv run python tests/byo_smoke.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ANTHROPIC_API_KEY"] = "stub-key"

import common.llm as llm


class _Blk:
    type = "text"
    def __init__(self, t): self.text = t
class _Usage:
    def __init__(self, i, o): self.input_tokens = i; self.output_tokens = o
class _Resp:
    def __init__(self, text, i, o): self.content = [_Blk(text)]; self.usage = _Usage(i, o)
class _Msgs:
    def create(self, *, model, system, max_tokens, temperature, messages):
        if "output-quality evaluator" in system:
            return _Resp('{"groundedness":0.9,"coherence":0.9,"hallucination":0.05}', 300, 40)
        # evaluator: cleared-with-cash → indefensible, else defensible
        user = messages[0]["content"]
        cleared = "DECISION: CLEAR" in user
        cash = "Cash deposits received" in user or "cash deposit amounts" in user
        if cleared and cash:
            j = ('{"material_features":["sub-$10k cash aggregating >$10k"],"criteria_in_play":["structuring"],'
                 '"defensible":false,"defensible_reasons":"structuring pattern requires escalation.",'
                 '"rationale_faithful":false,"rationale_faithful_reasons":"ignores the pattern.",'
                 '"soundness_confidence":0.1,"flag_for_review":true,"flag_explanation":"indefensible clearance.",'
                 '"examiner_note":"Textbook structuring cleared; BSA requires escalation."}')
        else:
            j = ('{"material_features":["within profile"],"criteria_in_play":["threshold review"],'
                 '"defensible":true,"defensible_reasons":"consistent with features.",'
                 '"rationale_faithful":true,"rationale_faithful_reasons":"matches basis.",'
                 '"soundness_confidence":0.85,"flag_for_review":false,"flag_explanation":"no issue.",'
                 '"examiner_note":"Consistent with profile; decision and rationale align."}')
        return _Resp(j, 700, 220)
class _Client:
    messages = _Msgs()


llm._client = lambda: _Client()

import run

sys.argv = ["run.py", "--agent", "logreplay", "--decisions", "samples/sample_decisions.csv"]
run.main()

# A BYO run must emit the same deliverable shapes as the reference run.
expected = [
    "results/BYO_REPORT.md",
    "results/ledger/byo_decision_ledger.md",
    "results/ledger/byo_assurance_summary.md",
    "results/finding/byo_attestation.json",
    "results/finding/byo_attestation.md",
    "results/runs/byo/decisions.jsonl",
]
missing = [p for p in expected if not Path(p).exists()]
if missing:
    raise AssertionError(f"BYO run did not emit: {missing}")
print(f"[byo smoke] OK — emitted {len(expected)} deliverables")
