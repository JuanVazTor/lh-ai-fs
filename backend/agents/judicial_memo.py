from __future__ import annotations

import json

from llm import call_llm
from schemas import VerificationFlag

from .base import Agent


class JudicialMemoAgent(Agent[str]):
    name = "JudicialMemoAgent"
    prompt = "Synthesize only high-confidence findings into one neutral paragraph for a judge. Do not overstate low-confidence citation issues."

    llm_prompt = """You are a judicial memo drafting agent.

Write one neutral paragraph for a judge summarizing the strongest verification issues. Use only the provided flags. Do not invent facts, citations, or procedural history. If there are no meaningful high-confidence issues, say so briefly.
"""

    def run(self, flags: list[VerificationFlag]) -> str:
        return call_llm(
            messages=[
                {"role": "system", "content": self.llm_prompt},
                {"role": "user", "content": json.dumps([flag.model_dump() for flag in flags])},
            ]
        )
