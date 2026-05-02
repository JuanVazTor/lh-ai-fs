from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ConfidenceLabel = Literal["low", "medium", "high"]
FindingStatus = Literal[
    "supported",
    "partially_supported",
    "not_supported",
    "could_not_verify",
    "likely_fabricated",
    "contradicted",
    "not_found",
]
Severity = Literal["low", "medium", "high"]


class ConfidenceMixin(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_label: ConfidenceLabel
    reasoning: str


class Citation(BaseModel):
    id: str
    citation_text: str
    authority_name: str
    reporter_or_statute: str | None = None
    proposition: str
    context: str
    line_start: int | None = None
    line_end: int | None = None
    has_direct_quote: bool = False
    direct_quote: str | None = None


class CitationVerification(ConfidenceMixin):
    citation_id: str
    status: FindingStatus
    issue: str | None = None
    source_basis: str


class QuoteCheck(ConfidenceMixin):
    citation_id: str
    quote: str
    status: FindingStatus
    issue: str | None = None
    source_basis: str


class FactClaim(BaseModel):
    id: str
    claim: str
    category: str
    context: str
    line_start: int | None = None
    line_end: int | None = None


class ConsistencyFinding(ConfidenceMixin):
    claim_id: str
    status: FindingStatus
    issue: str | None = None
    msj_claim: str
    source_document: str | None = None
    source_evidence: str | None = None
    source_basis: str


class VerificationFlag(ConfidenceMixin):
    id: str
    kind: Literal["citation", "quote", "fact"]
    severity: Severity
    title: str
    status: FindingStatus
    details: str
    source_ids: list[str] = Field(default_factory=list)
    source_basis: str


class AgentError(BaseModel):
    agent: str
    message: str
    recoverable: bool = True


class ReportMetadata(BaseModel):
    document_count: int
    agents_run: list[str] = Field(default_factory=list)


class VerificationReport(BaseModel):
    case_name: str
    judicial_memo: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    citation_verifications: list[CitationVerification] = Field(default_factory=list)
    quote_checks: list[QuoteCheck] = Field(default_factory=list)
    fact_claims: list[FactClaim] = Field(default_factory=list)
    consistency_findings: list[ConsistencyFinding] = Field(default_factory=list)
    flags: list[VerificationFlag] = Field(default_factory=list)
    agent_errors: list[AgentError] = Field(default_factory=list)
    metadata: ReportMetadata
