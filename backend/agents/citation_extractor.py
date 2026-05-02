from __future__ import annotations

from llm import call_llm_json
from pydantic import BaseModel, TypeAdapter
from schemas import Citation

from .base import Agent


class CitationExtractionResult(BaseModel):
    citations: list[Citation]


class CitationExtractorAgent(Agent[list[Citation]]):
    name = "CitationExtractorAgent"
    prompt = "Extract legal citations from the MSJ with the proposition each citation is used to support. Return structured citations only."

    llm_prompt = """You are a legal citation extraction agent. Extract every legal citation from the Motion for Summary Judgment.

Return JSON only with this shape:
{
  "citations": [
    {
      "id": "citation_1",
      "citation_text": "full citation text as it appears",
      "authority_name": "case or statute name",
      "reporter_or_statute": "reporter/statutory citation or null",
      "proposition": "the proposition the MSJ uses this citation to support",
      "context": "short surrounding MSJ text",
      "line_start": 1,
      "line_end": 1,
      "has_direct_quote": false,
      "direct_quote": null
    }
  ]
}

Rules:
- Extract citations only from the MSJ, not from your own legal knowledge.
- Include Id. citations when they are used as authority.
- If a direct quote appears in the same sentence or line, put the exact quoted text in direct_quote.
- Do not verify whether the citation is correct. This agent only extracts.
"""

    def run(self, motion_text: str) -> list[Citation]:
        result = call_llm_json(
            messages=[
                {"role": "system", "content": self.llm_prompt},
                {"role": "user", "content": motion_text},
            ],
            adapter=TypeAdapter(CitationExtractionResult),
        )
        return [citation.model_copy(update={"id": f"citation_{index}"}) for index, citation in enumerate(result.citations, start=1)]
