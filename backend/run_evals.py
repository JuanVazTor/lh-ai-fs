from __future__ import annotations

import json
from pathlib import Path

from agents import run_analysis


DOCUMENTS_DIR = Path(__file__).parent / "documents"

GOLD_FINDINGS = {
    "date_discrepancy": {
        "description": "MSJ says March 14, while source documents say March 12.",
        "accepted_statuses": {"contradicted"},
    },
    "ppe_discrepancy": {
        "description": "MSJ says Rivera lacked PPE, while police and witness documents say he wore required safety gear.",
        "accepted_statuses": {"contradicted"},
    },
    "osha_compliance_unverified": {
        "description": "MSJ's claimed OSHA inspection/compliance history is not verified by the provided case documents.",
        "accepted_statuses": {"not_found", "could_not_verify"},
    },
    "harmon_control_disputed": {
        "description": "MSJ frames Apex as exclusively controlling scaffolding, but source records show Harmon directed work and was told of concerns.",
        "accepted_statuses": {"partially_supported", "contradicted"},
    },
    "privette_quote_overbroad": {
        "description": "MSJ quotes Privette as an absolute never-liable rule, which is materially overbroad.",
        "accepted_statuses": {"not_supported"},
    },
    "limitations_argument_weak": {
        "description": "The time-bar framing is weak because the asserted filing date is within two years of the source-document incident date.",
        "accepted_statuses": {"contradicted", "not_supported"},
    },
}


def load_documents() -> dict[str, str]:
    return {path.stem: path.read_text() for path in DOCUMENTS_DIR.glob("*.txt")}


def run() -> dict:
    report = run_analysis(load_documents())
    flags = {flag.id: flag for flag in report.flags}
    matched = []
    missed = []

    for gold_id, expected in GOLD_FINDINGS.items():
        flag = flags.get(gold_id)
        if flag and flag.status in expected["accepted_statuses"]:
            matched.append(gold_id)
        else:
            missed.append(gold_id)

    hallucinated = []
    for flag in report.flags:
        if flag.id not in GOLD_FINDINGS and flag.status not in {"could_not_verify", "not_found"}:
            hallucinated.append(flag.id)

    total_flags = len(report.flags)
    precision = len(matched) / total_flags if total_flags else 0.0
    recall = len(matched) / len(GOLD_FINDINGS)
    hallucination_rate = len(hallucinated) / total_flags if total_flags else 0.0

    return {
        "metrics": {
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "hallucination_rate": round(hallucination_rate, 3),
            "matched_count": len(matched),
            "gold_count": len(GOLD_FINDINGS),
            "flag_count": total_flags,
        },
        "matched": matched,
        "missed": missed,
        "hallucinated": hallucinated,
        "agent_errors": [error.model_dump() for error in report.agent_errors],
        "flags": [flag.model_dump() for flag in report.flags],
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result["missed"] else 0)
