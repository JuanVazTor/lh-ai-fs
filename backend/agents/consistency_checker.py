from __future__ import annotations

import json

from llm import call_llm_json
from pydantic import BaseModel, TypeAdapter
from schemas import ConsistencyFinding, FactClaim

from .base import Agent


class ConsistencyCheckResult(BaseModel):
    consistency_findings: list[ConsistencyFinding]


class ConsistencyCheckerAgent(Agent[list[ConsistencyFinding]]):
    name = "ConsistencyCheckerAgent"
    prompt = "Compare structured MSJ fact claims against police, medical, and witness records. Return contradictions, support, or could_not_verify with evidence snippets."

    llm_prompt = """You are a cross-document legal fact consistency agent.

Given factual claims extracted from a Motion for Summary Judgment and the source case-file documents, compare each claim against the source documents.

Return JSON only with this shape:
{
  "consistency_findings": [
    {
      "claim_id": "same id as input claim",
      "status": "supported|partially_supported|contradicted|not_found|could_not_verify",
      "issue": "short issue or null",
      "msj_claim": "the input MSJ claim",
      "source_document": "document name or semicolon-separated names, or null",
      "source_evidence": "exact supporting/contradicting source snippet, or null",
      "source_basis": "concise explanation of the comparison",
      "confidence": 0.0,
      "confidence_label": "low|medium|high",
      "reasoning": "concise explanation"
    }
  ]
}

Rules:
- Return one finding per input claim.
- Use only the provided source documents as evidence.
- Prefer exact source snippets for source_evidence.
- Mark contradicted only when source documents conflict with the MSJ claim.
- Mark not_found when the source set does not contain evidence for the MSJ claim.
- Do not add claims that were not in the input.
"""

    def run(self, claims: list[FactClaim], documents: dict[str, str]) -> list[ConsistencyFinding]:
        if not claims:
            return []
        result = call_llm_json(
            messages=[
                {"role": "system", "content": self.llm_prompt},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "claims": [claim.model_dump() for claim in claims],
                            "documents": documents,
                        }
                    ),
                },
            ],
            adapter=TypeAdapter(ConsistencyCheckResult),
        )
        return result.consistency_findings
