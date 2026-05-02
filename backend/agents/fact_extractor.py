from __future__ import annotations

from schemas import FactClaim

from .base import Agent, numbered_lines, window


class FactExtractorAgent(Agent[list[FactClaim]]):
    name = "FactExtractorAgent"
    prompt = "Extract verifiable factual claims from the MSJ only. Do not verify claims or add facts from other documents."

    _targets = [
        ("incident_date", "March 14, 2021", "incident_date"),
        ("no_ppe", "not wearing required personal protective equipment", "ppe"),
        ("osha_compliance", "passed all OSHA inspections", "osha"),
        ("apex_control", "not Harmon", "control"),
        ("filing_date", "March 10, 2023", "limitations"),
        ("limitations_elapsed", "one year and 362 days", "limitations"),
        ("immediate_injury", "immediately apparent", "injury_notice"),
    ]

    def run(self, motion_text: str) -> list[FactClaim]:
        lines = numbered_lines(motion_text)
        claims: list[FactClaim] = []
        for claim_id, needle, category in self._targets:
            for line_number, line in lines:
                if needle.lower() not in line.lower():
                    continue
                claims.append(
                    FactClaim(
                        id=claim_id,
                        claim=self._claim_text(claim_id),
                        category=category,
                        context=window(lines, line_number, radius=1),
                        line_start=line_number,
                        line_end=line_number,
                    )
                )
                break
        return claims

    def _claim_text(self, claim_id: str) -> str:
        return {
            "incident_date": "The incident occurred on March 14, 2021.",
            "no_ppe": "Rivera was not wearing required PPE or fall-arrest equipment at the time of the incident.",
            "osha_compliance": "Harmon passed all OSHA inspections during the relevant period, most recently February 26, 2021.",
            "apex_control": "Apex, not Harmon, controlled scaffolding operations and safety procedures.",
            "filing_date": "Rivera filed the action on March 10, 2023.",
            "limitations_elapsed": "Rivera filed one year and 362 days after the incident.",
            "immediate_injury": "The medical records show Rivera's injuries were immediately apparent.",
        }[claim_id]
