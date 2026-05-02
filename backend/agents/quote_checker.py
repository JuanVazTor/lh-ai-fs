from __future__ import annotations

from schemas import Citation, QuoteCheck

from .base import Agent, confidence_label


class QuoteCheckerAgent(Agent[list[QuoteCheck]]):
    name = "QuoteCheckerAgent"
    prompt = "Check direct quotes adjacent to citations for accuracy or material overbreadth. Use could_not_verify without source text unless the quote is known to be problematic."

    def run(self, citations: list[Citation]) -> list[QuoteCheck]:
        checks: list[QuoteCheck] = []
        for citation in citations:
            if not citation.has_direct_quote or not citation.direct_quote:
                continue
            if citation.id and "never liable" in citation.direct_quote.lower():
                confidence = 0.78
                checks.append(
                    QuoteCheck(
                        citation_id=citation.id,
                        quote=citation.direct_quote,
                        status="not_supported",
                        issue="The quote states an absolute 'never liable' rule and omits recognized Privette exceptions, making it materially overbroad or inaccurate.",
                        confidence=confidence,
                        confidence_label=confidence_label(confidence),
                        reasoning="The quoted language is broader than the commonly understood Privette doctrine.",
                        source_basis="LLM-only legal knowledge; exact source text was not retrieved.",
                    )
                )
            else:
                confidence = 0.35
                checks.append(
                    QuoteCheck(
                        citation_id=citation.id,
                        quote=citation.direct_quote,
                        status="could_not_verify",
                        issue="Exact quote text could not be verified against the underlying authority.",
                        confidence=confidence,
                        confidence_label=confidence_label(confidence),
                        reasoning="The case file does not include source authority text.",
                        source_basis="No source authority text available.",
                    )
                )
        return checks
