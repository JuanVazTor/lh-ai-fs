from __future__ import annotations

import json

from llm import call_llm_json
from pydantic import BaseModel, TypeAdapter
from schemas import Citation, QuoteCheck

from .base import Agent


class QuoteCheckResult(BaseModel):
    quote_checks: list[QuoteCheck]


class QuoteCheckerAgent(Agent[list[QuoteCheck]]):
    name = "QuoteCheckerAgent"
    prompt = "Check direct quotes adjacent to citations for accuracy or material overbreadth. Use could_not_verify without source text unless the quote is known to be problematic."

    llm_prompt = """You are a legal quote checking agent.

Given extracted citations, review only citations that include direct_quote. Assess whether the quote is accurate, materially overbroad, unsupported, or impossible to verify from the available information.

Return JSON only with this shape:
{
  "quote_checks": [
    {
      "citation_id": "citation_1",
      "quote": "quoted text",
      "status": "supported|partially_supported|not_supported|could_not_verify|likely_fabricated",
      "issue": "short issue or null",
      "source_basis": "what you relied on",
      "confidence": 0.0,
      "confidence_label": "low|medium|high",
      "reasoning": "concise explanation"
    }
  ]
}

Rules:
- Return checks only for citations with direct_quote.
- Do not claim exact quote verification unless primary source text is present.
- If a quote appears materially broader than the legal rule, flag that explicitly.
- Use could_not_verify when source text is unavailable and you lack a confident basis.
"""

    def run(self, citations: list[Citation]) -> list[QuoteCheck]:
        quoted_citations = [citation for citation in citations if citation.has_direct_quote and citation.direct_quote]
        if not quoted_citations:
            return []
        result = call_llm_json(
            messages=[
                {"role": "system", "content": self.llm_prompt},
                {"role": "user", "content": json.dumps([citation.model_dump() for citation in quoted_citations])},
            ],
            adapter=TypeAdapter(QuoteCheckResult),
        )
        return result.quote_checks
