from __future__ import annotations

from llm import call_llm_json
from pydantic import BaseModel, TypeAdapter
from schemas import FactClaim

from .base import Agent


class FactExtractionResult(BaseModel):
    fact_claims: list[FactClaim]


class FactExtractorAgent(Agent[list[FactClaim]]):
    name = "FactExtractorAgent"
    prompt = "Extract verifiable factual claims from the MSJ only. Do not verify claims or add facts from other documents."

    llm_prompt = """You are a legal fact extraction agent. Extract factual claims from the Motion for Summary Judgment that could be verified against source documents.

Return JSON only with this shape:
{
  "fact_claims": [
    {
      "id": "short_snake_case_id",
      "claim": "verifiable factual assertion from the MSJ",
      "category": "incident_date|ppe|osha|control|limitations|injury_notice|other",
      "context": "short surrounding MSJ text",
      "line_start": 1,
      "line_end": 1
    }
  ]
}

Rules:
- Extract claims from the MSJ only.
- Do not verify the claims.
- Prefer factual premises over legal conclusions.
- Include dates, PPE assertions, OSHA/inspection assertions, control/supervision assertions, filing dates, and injury-notice assertions.
- Use stable, descriptive snake_case ids because downstream agents and evals refer to claim ids.
"""

    def run(self, motion_text: str) -> list[FactClaim]:
        result = call_llm_json(
            messages=[
                {"role": "system", "content": self.llm_prompt},
                {"role": "user", "content": motion_text},
            ],
            adapter=TypeAdapter(FactExtractionResult),
        )
        return result.fact_claims
