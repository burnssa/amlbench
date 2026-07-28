"""Quantify ground-truth leakage in agent-visible strings — NO model calls.

Fits a bag-of-words logistic regression predicting the rule label from each
agent-visible string, with and without the alert-ID token, plus an ID-prefix
rule classifier. High AUC with the ID and materially lower AUC without it =
the ID carries label signal any capable model can read.

    uv run --with scikit-learn python tools/leak_check.py [--alerts data/alerts.jsonl]

Surfaces checked:
  present_alert   — the standard triage prompt (agent/triage.py)
  narrative       — the narrative alone (what cover-weaving preserves)
  ledger          — interp ledger-mode presentation (interp/presentation.py)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from agent.triage import present_alert  # noqa: E402
from interp.presentation import present_alert_ledger  # noqa: E402

ID_RE = re.compile(r"\b[A-Z][A-Z0-9_]*-\d{4}\b")  # e.g. STRUCTURING_SUBTLE-0003, NORM-0079


def strip_ids(text: str) -> str:
    return ID_RE.sub("ALERT-REDACTED", text)


def id_rule_classifier(alert: dict) -> int:
    """Predict from the ID prefix alone: benign iff NORM-/BENIGN_*."""
    prefix = alert["alert_id"].split("-")[-2] if "-" in alert["alert_id"] else ""
    aid = alert["alert_id"]
    return 0 if ("NORM" in aid or "BENIGN" in aid) else 1


def bow_auc(texts: list[str], y, seed=0) -> float:
    from sklearn.feature_extraction.text import CountVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import cross_val_predict

    X = CountVectorizer(lowercase=True, token_pattern=r"[A-Za-z_]{2,}", max_features=5000
                        ).fit_transform(texts)
    scores = cross_val_predict(LogisticRegression(max_iter=2000, C=1.0), X, y,
                               cv=5, method="decision_function")
    return float(roc_auc_score(y, scores))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--alerts", default=str(REPO_ROOT / "data" / "alerts.jsonl"))
    args = ap.parse_args()

    alerts = [json.loads(l) for l in Path(args.alerts).read_text().splitlines() if l.strip()]
    y = [1 if a["ground_truth"]["label"] == "SHOULD_ESCALATE" else 0 for a in alerts]
    print(f"{len(alerts)} alerts ({sum(y)} reportable) from {args.alerts}\n")

    from sklearn.metrics import accuracy_score
    id_pred = [id_rule_classifier(a) for a in alerts]
    print(f"ID-prefix rule alone:            accuracy {accuracy_score(y, id_pred):.3f}")

    surfaces = {
        "present_alert (standard prompt)": [present_alert(a) for a in alerts],
        "narrative only":                  [a["narrative"] for a in alerts],
        "ledger presentation":             [present_alert_ledger(a) for a in alerts],
    }
    print(f"\n{'surface':<34} {'AUC with ID':>12} {'AUC no ID':>10}")
    for name, texts in surfaces.items():
        with_id = bow_auc(texts, y)
        no_id = bow_auc([strip_ids(t) for t in texts], y)
        print(f"{name:<34} {with_id:>12.3f} {no_id:>10.3f}")
    print("\nAUC(no ID) > 0.5 residual = template/summary features (e.g. the "
          "profile-consistency line in the standard presentation), reported separately "
          "in LIMITATIONS.md; the with/without gap is the ID leak itself.")


if __name__ == "__main__":
    main()
