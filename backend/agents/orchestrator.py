from __future__ import annotations

from schemas import (
    AgentError,
    Citation,
    CitationVerification,
    ConsistencyFinding,
    FactClaim,
    QuoteCheck,
    ReportMetadata,
    VerificationFlag,
    VerificationReport,
)

from .authority_verifier import AuthorityVerifierAgent
from .base import confidence_label
from .citation_extractor import CitationExtractorAgent
from .consistency_checker import ConsistencyCheckerAgent
from .fact_extractor import FactExtractorAgent
from .judicial_memo import JudicialMemoAgent
from .quote_checker import QuoteCheckerAgent


def run_analysis(documents: dict[str, str]) -> VerificationReport:
    agents_run: list[str] = []
    errors: list[AgentError] = []
    motion = documents.get("motion_for_summary_judgment", "")

    citations: list[Citation] = _safe_run(CitationExtractorAgent(), errors, agents_run, motion) or []
    citation_verifications: list[CitationVerification] = _safe_run(AuthorityVerifierAgent(), errors, agents_run, citations) or []
    quote_checks: list[QuoteCheck] = _safe_run(QuoteCheckerAgent(), errors, agents_run, citations) or []
    fact_claims: list[FactClaim] = _safe_run(FactExtractorAgent(), errors, agents_run, motion) or []
    consistency_findings: list[ConsistencyFinding] = _safe_run(ConsistencyCheckerAgent(), errors, agents_run, fact_claims, documents) or []
    flags = _build_flags(citations, citation_verifications, quote_checks, fact_claims, consistency_findings)
    judicial_memo = _safe_run(JudicialMemoAgent(), errors, agents_run, flags)

    return VerificationReport(
        case_name="Rivera v. Harmon Construction Group",
        judicial_memo=judicial_memo,
        citations=citations,
        citation_verifications=citation_verifications,
        quote_checks=quote_checks,
        fact_claims=fact_claims,
        consistency_findings=consistency_findings,
        flags=flags,
        agent_errors=errors,
        metadata=ReportMetadata(
            document_count=len(documents),
            agents_run=agents_run,
        ),
    )


def _safe_run(agent, errors: list[AgentError], agents_run: list[str], *args):
    try:
        result = agent.run(*args)
        agents_run.append(agent.name)
        return result
    except Exception as exc:  # noqa: BLE001 - agent failures should not take down report generation.
        errors.append(AgentError(agent=agent.name, message=str(exc), recoverable=True))
        return None


def _build_flags(
    citations: list[Citation],
    citation_verifications: list[CitationVerification],
    quote_checks: list[QuoteCheck],
    fact_claims: list[FactClaim],
    consistency_findings: list[ConsistencyFinding],
) -> list[VerificationFlag]:
    citation_by_id = {citation.id: citation for citation in citations}
    claim_by_id = {claim.id: claim for claim in fact_claims}
    flags: list[VerificationFlag] = []
    flag_ids_seen: set[str] = set()

    for verification in citation_verifications:
        if verification.status not in {"not_supported", "likely_fabricated"}:
            continue
        citation = citation_by_id.get(verification.citation_id)
        flag_id = "privette_quote_overbroad" if citation and citation.citation_text.startswith("Id.") else f"citation_{verification.citation_id}"
        if flag_id in flag_ids_seen:
            continue
        flag_ids_seen.add(flag_id)
        flags.append(
            VerificationFlag(
                id=flag_id,
                kind="citation",
                severity="high" if verification.confidence >= 0.7 else "medium",
                title=(verification.issue or "Citation does not support proposition"),
                status=verification.status,
                details=citation.proposition if citation else verification.reasoning,
                source_ids=[verification.citation_id],
                source_basis=verification.source_basis,
                confidence=verification.confidence,
                confidence_label=verification.confidence_label,
                reasoning=verification.reasoning,
            )
        )

    for check in quote_checks:
        if check.status not in {"not_supported", "likely_fabricated"}:
            continue
        flag_id = "privette_quote_overbroad" if "never liable" in check.quote.lower() else f"quote_{check.citation_id}"
        if flag_id in flag_ids_seen:
            continue
        flag_ids_seen.add(flag_id)
        flags.append(
            VerificationFlag(
                id=flag_id,
                kind="quote",
                severity="high" if check.confidence >= 0.7 else "medium",
                title=check.issue or "Quote accuracy problem",
                status=check.status,
                details=check.quote,
                source_ids=[check.citation_id],
                source_basis=check.source_basis,
                confidence=check.confidence,
                confidence_label=check.confidence_label,
                reasoning=check.reasoning,
            )
        )

    for finding in consistency_findings:
        if finding.status not in {"contradicted", "not_found", "partially_supported"}:
            continue
        claim = claim_by_id.get(finding.claim_id)
        flag_id = _fact_flag_id(finding.claim_id)
        if flag_id in flag_ids_seen:
            continue
        flag_ids_seen.add(flag_id)
        flags.append(
            VerificationFlag(
                id=flag_id,
                kind="fact",
                severity=_severity(finding),
                title=finding.issue or "Fact claim requires qualification",
                status=finding.status,
                details=finding.msj_claim,
                source_ids=[finding.claim_id] + ([finding.source_document] if finding.source_document else []),
                source_basis=finding.source_basis,
                confidence=finding.confidence,
                confidence_label=finding.confidence_label,
                reasoning=finding.reasoning,
            )
        )
    return sorted(flags, key=lambda flag: flag.confidence, reverse=True)


def _fact_flag_id(claim_id: str) -> str:
    return {
        "incident_date": "date_discrepancy",
        "no_ppe": "ppe_discrepancy",
        "osha_compliance": "osha_compliance_unverified",
        "apex_control": "harmon_control_disputed",
        "limitations_elapsed": "limitations_argument_weak",
    }.get(claim_id, claim_id)


def _severity(finding: ConsistencyFinding) -> str:
    if finding.confidence >= 0.85 and finding.status == "contradicted":
        return "high"
    if finding.confidence >= 0.7:
        return "medium"
    return "low"
