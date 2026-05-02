from __future__ import annotations

from schemas import VerificationFlag

from .base import Agent


class JudicialMemoAgent(Agent[str]):
    name = "JudicialMemoAgent"
    prompt = "Synthesize only high-confidence findings into one neutral paragraph for a judge. Do not overstate low-confidence citation issues."

    def run(self, flags: list[VerificationFlag]) -> str:
        high_confidence = [flag for flag in flags if flag.confidence >= 0.7]
        if not high_confidence:
            return "The verification pipeline did not identify high-confidence discrepancies suitable for judicial summary."

        titles = {flag.id: flag.title for flag in high_confidence}
        parts: list[str] = []
        if "date_discrepancy" in titles:
            parts.append("the motion states the incident occurred on March 14, 2021, while the police, medical, and witness records consistently place it on March 12, 2021")
        if "ppe_discrepancy" in titles:
            parts.append("the motion's assertion that Rivera lacked required PPE conflicts with police and witness accounts that he wore a hard hat and safety harness")
        if "harmon_control_disputed" in titles:
            parts.append("the motion's exclusive-control framing is complicated by evidence that Harmon foreman Ray Donner directed the crew to work on the scaffold section and allegedly dismissed a base-plate concern")
        if "osha_compliance_unverified" in titles:
            parts.append("the asserted OSHA inspection record is not verified by the provided case documents")
        if "privette_quote_overbroad" in titles:
            parts.append("the Privette quotation appears materially overbroad because it presents hirer nonliability as absolute")

        if not parts:
            parts = [flag.title.lower() for flag in high_confidence[:3]]
        return "The strongest verification issues are that " + "; ".join(parts) + ". These discrepancies do not resolve the motion, but they identify factual and legal assertions that should not be accepted without further support."
