from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agents import run_analysis
from schemas import VerificationFlag, VerificationReport


DOCUMENTS_DIR = Path(__file__).parent / "documents"


@dataclass(frozen=True)
class ExpectedFinding:
    id: str
    description: str
    accepted_statuses: set[str]
    required_concepts: tuple[tuple[str, ...], ...]
    min_confidence: float = 0.0
    max_confidence: float = 1.0


GOLD_FINDINGS = [
    ExpectedFinding(
        id="date_discrepancy",
        description="MSJ says March 14, while source documents say March 12.",
        accepted_statuses={"contradicted", "partially_supported"},
        required_concepts=(("march 14",), ("march 12",), ("date", "incident")),
        min_confidence=0.5,
    ),
    ExpectedFinding(
        id="ppe_discrepancy",
        description="MSJ says Rivera lacked PPE, while police and witness documents say he wore required safety gear.",
        accepted_statuses={"contradicted", "partially_supported"},
        required_concepts=(("ppe", "personal protective", "hard hat", "harness"), ("wearing", "wore"), ("not wearing", "lacked", "not worn")),
        min_confidence=0.5,
    ),
    ExpectedFinding(
        id="osha_compliance_unverified",
        description="MSJ's claimed OSHA inspection/compliance history is not verified by the provided case documents.",
        accepted_statuses={"not_found", "could_not_verify"},
        required_concepts=(("osha",), ("not verify", "not verified", "could not verify", "not found", "unverified")),
        min_confidence=0.5,
        max_confidence=0.85,
    ),
    ExpectedFinding(
        id="harmon_control_disputed",
        description="MSJ frames Apex as exclusively controlling scaffolding, but source records show Harmon directed work and was told of concerns.",
        accepted_statuses={"partially_supported", "contradicted"},
        required_concepts=(("harmon", "donner"), ("directed", "control", "foreman"), ("apex", "exclusive", "scaffold")),
        min_confidence=0.5,
    ),
    ExpectedFinding(
        id="privette_quote_overbroad",
        description="MSJ quotes Privette as an absolute never-liable rule, which is materially overbroad.",
        accepted_statuses={"not_supported"},
        required_concepts=(("privette",), ("never liable", "absolute", "categorical"), ("overbroad", "exceptions", "not supported")),
        min_confidence=0.6,
        max_confidence=0.85,
    ),
    ExpectedFinding(
        id="limitations_argument_weak",
        description="The time-bar framing is weak because the asserted filing date is within two years of the source-document incident date.",
        accepted_statuses={"contradicted", "not_supported", "partially_supported"},
        required_concepts=(("limitations", "time-bar", "filing"), ("two years", "within two", "march 10"), ("march 12", "march 14", "incident")),
        min_confidence=0.5,
    ),
]

ASPIRATIONAL_FINDINGS = [
    ExpectedFinding(
        id="seabright_insulation_overstatement",
        description="The MSJ uses Seabright plus OSHA compliance to suggest effective insulation from tort liability, which is stronger than the authority supports.",
        accepted_statuses={"not_supported", "partially_supported"},
        required_concepts=(("seabright",), ("insulat", "tort liability", "osha")),
        min_confidence=0.5,
        max_confidence=0.85,
    ),
]

NEGATIVE_ASSERTIONS = [
    "Rivera was employed by Apex",
    "2200 West Olympic Boulevard",
    "left leg, lower back, and left wrist",
]

UNCERTAINTY_EXPECTATIONS = {
    "Whitmore": {"could_not_verify"},
    "Kellerman": {"could_not_verify"},
    "Torres": {"could_not_verify"},
}


def load_documents() -> dict[str, str]:
    return {path.stem: path.read_text() for path in DOCUMENTS_DIR.glob("*.txt")}


def run() -> dict[str, Any]:
    documents = load_documents()
    report = run_analysis(documents)

    gold_result = score_expected_findings(report, GOLD_FINDINGS)
    aspirational_result = score_expected_findings(report, ASPIRATIONAL_FINDINGS)
    negative_result = score_negative_assertions(report)
    grounding_result = score_grounding(report, documents)
    uncertainty_result = score_uncertainty(report)
    mutation_result = score_mutations(documents)
    limitation_result = score_known_limitations(report)
    adversarial_result = score_adversarial_cases(documents)

    total_flags = len(report.flags)
    matched_count = len(gold_result["matched"])
    weak_match_count = len(gold_result["weak_matches"])
    total_expected_count = len(GOLD_FINDINGS) + len(ASPIRATIONAL_FINDINGS)
    total_matched_count = matched_count + len(aspirational_result["matched"])
    total_semantic_match_count = total_matched_count + weak_match_count + len(aspirational_result["weak_matches"])
    hallucination_result = score_hallucinations(report, GOLD_FINDINGS + ASPIRATIONAL_FINDINGS, grounding_result)
    hallucinated_count = len(hallucination_result["hallucinated_flags"]) + len(negative_result["false_positive_negative_assertions"])

    metrics = {
        "precision": round(total_semantic_match_count / total_flags, 3) if total_flags else 0.0,
        "core_recall": round(matched_count / len(GOLD_FINDINGS), 3),
        "expanded_recall": round(total_matched_count / total_expected_count, 3),
        "weak_match_count": weak_match_count,
        "hallucination_rate": round(hallucinated_count / total_flags, 3) if total_flags else 0.0,
        "evidence_grounding_rate": grounding_result["grounding_rate"],
        "uncertainty_accuracy": uncertainty_result["accuracy"],
        "mutation_pass_rate": mutation_result["pass_rate"],
        "clean_case_false_positive_rate": adversarial_result["clean_case_false_positive_rate"],
        "fabricated_citation_detection_rate": adversarial_result["fabricated_citation_detection_rate"],
        "citation_extraction_recall": limitation_result["citation_extraction_recall"],
        "authority_source_grounding_rate": limitation_result["authority_source_grounding_rate"],
        "quote_exact_verification_rate": limitation_result["quote_exact_verification_rate"],
        "matched_count": matched_count,
        "gold_count": len(GOLD_FINDINGS),
        "expanded_matched_count": total_matched_count,
        "expanded_expected_count": total_expected_count,
        "flag_count": total_flags,
    }

    return {
        "metrics": metrics,
        "core_gold": gold_result,
        "aspirational": aspirational_result,
        "negative_assertions": negative_result,
        "grounding": grounding_result,
        "hallucinations": hallucination_result,
        "uncertainty": uncertainty_result,
        "mutations": mutation_result,
        "adversarial_cases": adversarial_result,
        "known_limitations": limitation_result,
        "agent_errors": [error.model_dump() for error in report.agent_errors],
        "flags": [flag.model_dump() for flag in report.flags],
    }


def score_expected_findings(report: VerificationReport, expected_findings: list[ExpectedFinding]) -> dict[str, Any]:
    matched = []
    missed = []
    weak_matches = []
    used_flag_ids: set[str] = set()

    for expected in expected_findings:
        candidates = [flag for flag in report.flags if flag.id not in used_flag_ids and concepts_present(expected, flag_text(flag))]
        flag = best_candidate(candidates)
        if flag is None:
            missed.append({"id": expected.id, "reason": "missing"})
            continue
        text = flag_text(flag)
        status_ok = flag.status in expected.accepted_statuses
        confidence_ok = expected.min_confidence <= flag.confidence <= expected.max_confidence
        used_flag_ids.add(flag.id)
        if status_ok and confidence_ok:
            matched.append({"id": expected.id, "flag_id": flag.id})
        else:
            weak_matches.append(
                {
                    "id": expected.id,
                    "flag_id": flag.id,
                    "status_ok": status_ok,
                    "concepts_present": True,
                    "confidence_ok": confidence_ok,
                    "actual_status": flag.status,
                    "actual_confidence": flag.confidence,
                }
            )

    return {"matched": matched, "missed": missed, "weak_matches": weak_matches}


def score_hallucinations(report: VerificationReport, expected_findings: list[ExpectedFinding], grounding_result: dict[str, Any]) -> dict[str, Any]:
    grounded_claim_ids = {record["claim_id"] for record in grounding_result["grounded_records"]}
    hallucinated = []
    for flag in report.flags:
        text = flag_text(flag)
        if flag.status in {"could_not_verify", "not_found"}:
            continue
        if any(concepts_present(expected, text) for expected in expected_findings):
            continue
        if flag.kind == "fact" and any(source_id in grounded_claim_ids for source_id in flag.source_ids):
            continue
        hallucinated.append({"flag_id": flag.id, "status": flag.status, "title": flag.title})
    return {"hallucinated_flags": hallucinated}


def score_negative_assertions(report: VerificationReport) -> dict[str, Any]:
    false_positives = []
    for assertion in NEGATIVE_ASSERTIONS:
        assertion_words = significant_words(assertion)
        for flag in report.flags:
            text = flag_text(flag)
            if all(word in text for word in assertion_words):
                false_positives.append({"assertion": assertion, "flag_id": flag.id})
    return {"checked": NEGATIVE_ASSERTIONS, "false_positive_negative_assertions": false_positives}


def score_grounding(report: VerificationReport, documents: dict[str, str]) -> dict[str, Any]:
    records = report.consistency_findings
    grounded = []
    ungrounded = []
    for finding in records:
        if not finding.source_evidence or not finding.source_document:
            continue
        source_names = [name.strip() for name in finding.source_document.split(";")]
        external_source_names = [name for name in source_names if name != "motion_for_summary_judgment"]
        found = any(finding.source_evidence in documents.get(name, "") for name in external_source_names)
        item = {"claim_id": finding.claim_id, "evidence": finding.source_evidence, "source_document": finding.source_document}
        if found:
            grounded.append(item)
        else:
            ungrounded.append(item)
    total = len(grounded) + len(ungrounded)
    return {
        "grounded_records": grounded,
        "ungrounded_records": ungrounded,
        "grounding_rate": round(len(grounded) / total, 3) if total else 1.0,
    }


def score_uncertainty(report: VerificationReport) -> dict[str, Any]:
    checks = []
    for citation in report.citations:
        expected_statuses = next((statuses for term, statuses in UNCERTAINTY_EXPECTATIONS.items() if term in citation.citation_text), None)
        if not expected_statuses:
            continue
        verification = next((item for item in report.citation_verifications if item.citation_id == citation.id), None)
        checks.append(
            {
                "citation": citation.citation_text,
                "expected_statuses": sorted(expected_statuses),
                "actual_status": verification.status if verification else None,
                "passed": bool(verification and verification.status in expected_statuses and verification.confidence <= 0.5),
            }
        )
    passed = sum(1 for check in checks if check["passed"])
    return {"checks": checks, "accuracy": round(passed / len(checks), 3) if checks else 1.0}


def score_mutations(documents: dict[str, str]) -> dict[str, Any]:
    scenarios = [
        {
            "name": "aligned_incident_date_removes_date_flag",
            "documents": mutate_motion(documents, "March 14, 2021", "March 12, 2021"),
            "absent_finding": GOLD_FINDINGS[0],
        },
        {
            "name": "aligned_ppe_removes_ppe_flag",
            "documents": mutate_motion(documents, "Rivera was not wearing required personal protective equipment", "Rivera was wearing required personal protective equipment"),
            "absent_finding": GOLD_FINDINGS[1],
        },
        {
            "name": "removed_harmon_direction_removes_control_flag",
            "documents": remove_harmon_direction(documents),
            "absent_finding": GOLD_FINDINGS[3],
        },
    ]
    results = []
    for scenario in scenarios:
        report = run_analysis(scenario["documents"])
        unexpected_flags = [flag.id for flag in report.flags if concepts_present(scenario["absent_finding"], flag_text(flag))]
        results.append(
            {
                "name": scenario["name"],
                "passed": not unexpected_flags,
                "unexpected_flags": unexpected_flags,
            }
        )
    passed = sum(1 for result in results if result["passed"])
    return {"scenarios": results, "pass_rate": round(passed / len(results), 3)}


def score_known_limitations(report: VerificationReport) -> dict[str, Any]:
    expected_citation_terms = [
        "Privette",
        "Id. at 702",
        "Whitmore",
        "Kellerman",
        "Seabright",
        "Section 335.1",
        "Torres",
        "Blackwell",
        "Dixon",
        "Okafor",
        "Nguyen",
        "Reeves",
    ]
    extracted_text = "\n".join(citation.citation_text for citation in report.citations)
    extracted_terms = [term for term in expected_citation_terms if term in extracted_text]

    source_grounded_authorities = [
        item for item in report.citation_verifications if has_primary_authority_text(item.source_basis)
    ]
    exact_quote_checks = [
        item for item in report.quote_checks if has_primary_authority_text(item.source_basis)
    ]

    return {
        "citation_extraction_recall": round(len(extracted_terms) / len(expected_citation_terms), 3),
        "extracted_citation_terms": extracted_terms,
        "missing_citation_terms": [term for term in expected_citation_terms if term not in extracted_terms],
        "authority_source_grounding_rate": round(len(source_grounded_authorities) / len(report.citation_verifications), 3) if report.citation_verifications else 0.0,
        "quote_exact_verification_rate": round(len(exact_quote_checks) / len(report.quote_checks), 3) if report.quote_checks else 0.0,
        "notes": [
            "Authority checks are not source-grounded because this implementation does not retrieve case-law text.",
            "Direct quote checks identify overbreadth but do not compare against primary-source quote text.",
            "Expanded recall includes one real issue the current flag layer does not yet promote: Seabright/OSHA insulation overstatement.",
        ],
    }


def score_adversarial_cases(documents: dict[str, str]) -> dict[str, Any]:
    clean_report = run_analysis(make_clean_case_documents())
    fabricated_report = run_analysis(make_fabricated_citation_documents(documents))

    clean_false_positive_flags = [
        flag.id
        for flag in clean_report.flags
        if flag.status in {"contradicted", "not_supported", "likely_fabricated"}
    ]
    fabricated_detected = any(
        verification.status == "likely_fabricated"
        for verification in fabricated_report.citation_verifications
    ) or any(flag.status == "likely_fabricated" for flag in fabricated_report.flags)

    return {
        "clean_case": {
            "false_positive_flags": clean_false_positive_flags,
            "flag_count": len(clean_report.flags),
        },
        "fabricated_citation_case": {
            "detected": fabricated_detected,
            "citations": [citation.model_dump() for citation in fabricated_report.citations],
            "citation_verifications": [verification.model_dump() for verification in fabricated_report.citation_verifications],
            "flags": [flag.model_dump() for flag in fabricated_report.flags],
        },
        "clean_case_false_positive_rate": round(len(clean_false_positive_flags) / max(len(clean_report.flags), 1), 3),
        "fabricated_citation_detection_rate": 1.0 if fabricated_detected else 0.0,
    }


def make_clean_case_documents() -> dict[str, str]:
    return {
        "motion_for_summary_judgment": """SUPERIOR COURT OF THE STATE OF CALIFORNIA
COUNTY OF LOS ANGELES

MARTIN LEE, Plaintiff, v. HARBOR BUILDERS, INC., Defendant.

I. STATEMENT OF FACTS

1. The incident occurred on May 5, 2022 at 100 Harbor Avenue.
2. Lee was employed by Safe Scaffold Services.
3. Lee was wearing required personal protective equipment, including a hard hat and safety harness.
4. Harbor Builders' site foreman did not direct Lee's scaffold work.

II. ARGUMENT

The undisputed source records confirm the relevant facts. California Code of Civil Procedure Section 335.1 provides a two-year limitations period for personal injury claims.
""",
        "police_report": """Date of Incident: May 5, 2022
Location: 100 Harbor Avenue
Lee was wearing a hard hat and harness. No Harbor Builders foreman directed the scaffold work.
""",
        "medical_records_excerpt": """DATE OF ADMISSION: May 5, 2022
Patient reported minor wrist pain after a scaffold incident at 100 Harbor Avenue.
""",
        "witness_statement": """The incident occurred on May 5, 2022. Lee wore his hard hat and safety harness. Harbor Builders did not direct our scaffold work.
""",
    }


def make_fabricated_citation_documents(documents: dict[str, str]) -> dict[str, str]:
    mutated = dict(documents)
    mutated["motion_for_summary_judgment"] = """SUPERIOR COURT OF THE STATE OF CALIFORNIA
COUNTY OF LOS ANGELES

CARLOS RIVERA, Plaintiff, v. HARMON CONSTRUCTION GROUP, INC., Defendant.

I. ARGUMENT

Harmon is immune from all scaffold-collapse claims because courts have adopted a categorical no-liability rule for general contractors. Imaginary Builders v. Phantom Safety, 999 F.9th 999 (9th Cir. 2099).
"""
    return mutated


def mutate_motion(documents: dict[str, str], old: str, new: str) -> dict[str, str]:
    mutated = dict(documents)
    mutated["motion_for_summary_judgment"] = mutated["motion_for_summary_judgment"].replace(old, new)
    return mutated


def remove_harmon_direction(documents: dict[str, str]) -> dict[str, str]:
    mutated = dict(documents)
    mutated["police_report"] = mutated["police_report"].replace("Donner stated that he had directed Rivera and his crew to begin work on the east-side scaffolding section earlier that morning.", "")
    mutated["police_report"] = mutated["police_report"].replace("Tran stated that these concerns were communicated to both Ellison and Donner.", "")
    mutated["witness_statement"] = mutated["witness_statement"].replace("During our morning coordination meeting, Ray Donner — the project foreman for Harmon Construction — told us that the east-side scaffolding section needed to be fully operational by end of day.", "")
    mutated["witness_statement"] = mutated["witness_statement"].replace("I also mentioned the base plate issue directly to Ray Donner. Donner told me, \"We don't have time to re-do the base. It's been fine. Just get up there and get it done.\"", "")
    mutated["witness_statement"] = mutated["witness_statement"].replace("I want to note that Donner had personally directed us to work on that section that morning and dismissed my concern about the base plate.", "")
    return mutated


def flag_text(flag: VerificationFlag) -> str:
    return " ".join([flag.id, flag.title, flag.details, flag.reasoning, flag.source_basis]).lower()


def concepts_present(expected: ExpectedFinding, text: str) -> bool:
    normalized = text.lower()
    return all(any(alias in normalized for alias in concept_aliases) for concept_aliases in expected.required_concepts)


def best_candidate(flags: list[VerificationFlag]) -> VerificationFlag | None:
    if not flags:
        return None
    return sorted(flags, key=lambda flag: flag.confidence, reverse=True)[0]


def has_primary_authority_text(source_basis: str) -> bool:
    basis = source_basis.lower()
    unavailable_markers = [
        "llm-only",
        "no source",
        "not retrieved",
        "without source",
        "no primary",
        "not available",
        "general legal knowledge",
    ]
    retrieval_markers = [
        "retrieved primary",
        "source text",
        "case text",
        "statutory text",
        "provided authority text",
    ]
    return any(marker in basis for marker in retrieval_markers) and not any(marker in basis for marker in unavailable_markers)


def significant_words(text: str) -> list[str]:
    ignored = {"the", "a", "an", "and", "or", "was", "by", "at", "of", "to", "in"}
    return [word.lower().strip(",.;:") for word in text.split() if word.lower().strip(",.;:") not in ignored]


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
    failed = bool(
        result["core_gold"]["missed"]
        or result["negative_assertions"]["false_positive_negative_assertions"]
        or result["grounding"]["ungrounded_records"]
        or result["hallucinations"]["hallucinated_flags"]
        or any(not scenario["passed"] for scenario in result["mutations"]["scenarios"])
    )
    raise SystemExit(1 if failed else 0)
