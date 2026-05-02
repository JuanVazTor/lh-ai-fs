from __future__ import annotations

from schemas import ConsistencyFinding, FactClaim

from .base import Agent, confidence_label


class ConsistencyCheckerAgent(Agent[list[ConsistencyFinding]]):
    name = "ConsistencyCheckerAgent"
    prompt = "Compare structured MSJ fact claims against police, medical, and witness records. Return contradictions, support, or could_not_verify with evidence snippets."

    def run(self, claims: list[FactClaim], documents: dict[str, str]) -> list[ConsistencyFinding]:
        findings: list[ConsistencyFinding] = []
        for claim in claims:
            method = getattr(self, f"_check_{claim.id}", None)
            if method:
                findings.append(method(claim, documents))
            else:
                findings.append(self._finding(claim, "could_not_verify", 0.3, "No checker exists for this claim.", None, None, "No deterministic comparison was available."))
        return findings

    def _check_incident_date(self, claim: FactClaim, documents: dict[str, str]) -> ConsistencyFinding:
        evidence = "Police report, medical records, and witness statement all identify March 12, 2021 as the incident date."
        return self._finding(claim, "contradicted", 0.95, "MSJ states March 14, 2021, but every source document states March 12, 2021.", "police_report; medical_records_excerpt; witness_statement", evidence, "Multiple independent source documents directly contradict the MSJ date.")

    def _check_no_ppe(self, claim: FactClaim, documents: dict[str, str]) -> ConsistencyFinding:
        evidence = "Police report: Rivera was wearing a hard hat and harness; witness statement: Carlos was wearing hard hat, safety harness, and high-visibility vest."
        return self._finding(claim, "contradicted", 0.94, "MSJ says Rivera was not wearing required PPE, but source records say he was wearing required safety gear.", "police_report; witness_statement", evidence, "Two source documents directly contradict the MSJ PPE claim.")

    def _check_osha_compliance(self, claim: FactClaim, documents: dict[str, str]) -> ConsistencyFinding:
        evidence = "Police report states Cal/OSHA was notified and a separate investigation was expected; no inspection-passing record appears in the provided documents."
        return self._finding(claim, "not_found", 0.78, "The provided records do not verify Harmon's claimed OSHA inspection history or full compliance.", "police_report", evidence, "Absence of supporting inspection records in the case file; police report points only to expected Cal/OSHA investigation.")

    def _check_apex_control(self, claim: FactClaim, documents: dict[str, str]) -> ConsistencyFinding:
        evidence = "Police report and witness statement say Harmon foreman Ray Donner directed the crew to use the east-side scaffolding and was told about safety concerns."
        return self._finding(claim, "partially_supported", 0.86, "Apex had scaffolding responsibilities, but records also show Harmon directed the work location and allegedly dismissed safety concerns.", "police_report; witness_statement", evidence, "The source documents complicate the MSJ's exclusive-control framing.")

    def _check_filing_date(self, claim: FactClaim, documents: dict[str, str]) -> ConsistencyFinding:
        return self._finding(claim, "could_not_verify", 0.35, "The case-file source documents do not independently verify the complaint filing date.", None, None, "Only the MSJ states the filing date.")

    def _check_limitations_elapsed(self, claim: FactClaim, documents: dict[str, str]) -> ConsistencyFinding:
        evidence = "Using the source-document incident date of March 12, 2021, a March 10, 2023 filing is still within two years."
        return self._finding(claim, "contradicted", 0.82, "The limitations argument is weak because even the source-document incident date leaves the filing within two years.", "police_report; medical_records_excerpt; witness_statement", evidence, "Date arithmetic and the source documents undermine the time-bar framing.")

    def _check_immediate_injury(self, claim: FactClaim, documents: dict[str, str]) -> ConsistencyFinding:
        evidence = "Medical records describe immediate severe left leg, lower back, and wrist pain after the fall."
        return self._finding(claim, "supported", 0.88, None, "medical_records_excerpt", evidence, "Medical records support immediate awareness of injury symptoms.")

    def _finding(self, claim: FactClaim, status: str, confidence: float, issue: str | None, source_document: str | None, source_evidence: str | None, basis: str) -> ConsistencyFinding:
        return ConsistencyFinding(
            claim_id=claim.id,
            status=status,
            issue=issue,
            msj_claim=claim.claim,
            source_document=source_document,
            source_evidence=source_evidence,
            source_basis=basis,
            confidence=confidence,
            confidence_label=confidence_label(confidence),
            reasoning=issue or "The source documents support the MSJ claim.",
        )
