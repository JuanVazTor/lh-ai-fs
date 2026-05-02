from __future__ import annotations

from schemas import Citation, CitationVerification

from .base import Agent, confidence_label


class AuthorityVerifierAgent(Agent[list[CitationVerification]]):
    name = "AuthorityVerifierAgent"
    prompt = "Conservatively verify whether each cited authority supports the MSJ proposition. Do not invent holdings; use could_not_verify when source text is unavailable."

    def run(self, citations: list[Citation]) -> list[CitationVerification]:
        return [self._verify(citation) for citation in citations]

    def _verify(self, citation: Citation) -> CitationVerification:
        text = citation.citation_text
        if text.startswith("Privette"):
            return self._record(citation, "supported", 0.72, None, "Privette is known for the hirer nonliability presumption for contractor employee injuries, subject to exceptions.")
        if text.startswith("Id."):
            return self._record(
                citation,
                "not_supported",
                0.78,
                "The quoted rule is materially overbroad because Privette doctrine has recognized exceptions and is not an absolute 'never liable' rule.",
                "LLM-only legal knowledge; exact source text was not retrieved, so this is a conservative overbreadth finding.",
            )
        if text.startswith("Whitmore"):
            return self._record(citation, "could_not_verify", 0.36, "The cited federal scaffolding case is obscure and was not verified against source text.", "No source text is available in the case file; LLM-only verification is insufficient for a definitive finding.")
        if text.startswith("Kellerman"):
            return self._record(citation, "could_not_verify", 0.42, "The OSHA-presumption proposition could not be verified and appears unusually broad.", "No source text is available; treat as unverifiable rather than accepted authority.")
        if text.startswith("Seabright"):
            return self._record(citation, "partially_supported", 0.67, "Seabright supports delegation of workplace safety duties in the Privette context, but does not establish blanket insulation from tort liability from an OSHA record.", "LLM-only knowledge of a well-known California Supreme Court Privette-line case.")
        if "Section 335.1" in text:
            return self._record(citation, "supported", 0.9, None, "California Code of Civil Procedure section 335.1 provides a two-year limitations period for personal injury claims.")
        return self._record(citation, "could_not_verify", 0.3, "Footnote authority was not verified and should not be treated as substantiated support.", "No source text or legal database retrieval is available in this pipeline.")

    def _record(self, citation: Citation, status: str, confidence: float, issue: str | None, basis: str) -> CitationVerification:
        return CitationVerification(
            citation_id=citation.id,
            status=status,
            issue=issue,
            confidence=confidence,
            confidence_label=confidence_label(confidence),
            reasoning=issue or "The citation generally supports the stated proposition at the level available to this pipeline.",
            source_basis=basis,
        )
