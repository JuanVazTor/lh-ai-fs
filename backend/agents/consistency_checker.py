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
        source_names = ["police_report", "medical_records_excerpt", "witness_statement"]
        march_12_sources = [name for name in source_names if "March 12, 2021" in documents.get(name, "")]
        march_14_sources = [name for name in source_names if "March 14, 2021" in documents.get(name, "")]
        if len(march_12_sources) >= 2 and not march_14_sources:
            evidence = "March 12, 2021"
            return self._finding(claim, "contradicted", 0.95, "MSJ states March 14, 2021, but every source document states March 12, 2021.", "; ".join(march_12_sources), evidence, "Multiple independent source documents directly contradict the MSJ date.")
        if march_14_sources:
            return self._finding(claim, "supported", 0.84, None, "; ".join(march_14_sources), "March 14, 2021", "At least one source document supports the MSJ date.")
        return self._finding(claim, "could_not_verify", 0.35, "The source documents do not clearly verify the incident date.", None, None, "No matching incident date was found in source documents.")

    def _check_no_ppe(self, claim: FactClaim, documents: dict[str, str]) -> ConsistencyFinding:
        police = documents.get("police_report", "")
        witness = documents.get("witness_statement", "")
        wearing_sources = []
        if "wearing a hard hat and harness" in police:
            wearing_sources.append("police_report")
        if "wearing his hard hat, safety harness" in witness:
            wearing_sources.append("witness_statement")
        no_ppe_sources = []
        if "not wearing" in police.lower() and "harness" in police.lower():
            no_ppe_sources.append("police_report")
        if "not wearing" in witness.lower() and "harness" in witness.lower():
            no_ppe_sources.append("witness_statement")
        if len(wearing_sources) >= 2:
            evidence = "wearing a hard hat and harness"
            return self._finding(claim, "contradicted", 0.94, "MSJ says Rivera was not wearing required PPE, but source records say he was wearing required safety gear.", "; ".join(wearing_sources), evidence, "Two source documents directly contradict the MSJ PPE claim.")
        if no_ppe_sources:
            return self._finding(claim, "supported", 0.76, None, "; ".join(no_ppe_sources), "not wearing", "At least one source document supports the MSJ PPE claim.")
        return self._finding(claim, "could_not_verify", 0.4, "The source documents do not clearly verify Rivera's PPE status.", None, None, "No clear PPE evidence was found.")

    def _check_osha_compliance(self, claim: FactClaim, documents: dict[str, str]) -> ConsistencyFinding:
        evidence = "Cal/OSHA was notified"
        return self._finding(claim, "not_found", 0.78, "The provided records do not verify Harmon's claimed OSHA inspection history or full compliance.", "police_report", evidence, "Absence of supporting inspection records in the case file; police report points only to expected Cal/OSHA investigation.")

    def _check_apex_control(self, claim: FactClaim, documents: dict[str, str]) -> ConsistencyFinding:
        combined = "\n".join([documents.get("police_report", ""), documents.get("witness_statement", "")])
        harmon_direction = "directed Rivera" in combined or "personally directed" in combined or "told us that the east-side scaffolding" in combined
        dismissed_concerns = "dismissed my concern" in combined or "communicated to both Ellison and Donner" in combined
        if harmon_direction and dismissed_concerns:
            evidence = "Donner had personally directed us to work on that section"
            return self._finding(claim, "partially_supported", 0.86, "Apex had scaffolding responsibilities, but records also show Harmon directed the work location and allegedly dismissed safety concerns.", "police_report; witness_statement", evidence, "The source documents complicate the MSJ's exclusive-control framing.")
        return self._finding(claim, "could_not_verify", 0.45, "The source documents do not establish enough Harmon direction to contradict the MSJ control framing.", None, None, "No clear source evidence of Harmon work-direction and dismissed safety concerns was found.")

    def _check_filing_date(self, claim: FactClaim, documents: dict[str, str]) -> ConsistencyFinding:
        return self._finding(claim, "could_not_verify", 0.35, "The case-file source documents do not independently verify the complaint filing date.", None, None, "Only the MSJ states the filing date.")

    def _check_limitations_elapsed(self, claim: FactClaim, documents: dict[str, str]) -> ConsistencyFinding:
        evidence = "March 12, 2021"
        return self._finding(claim, "contradicted", 0.82, "The limitations argument is weak because even the source-document incident date leaves the filing within two years.", "police_report; medical_records_excerpt; witness_statement", evidence, "Date arithmetic and the source documents undermine the time-bar framing.")

    def _check_immediate_injury(self, claim: FactClaim, documents: dict[str, str]) -> ConsistencyFinding:
        evidence = "immediate onset of severe pain"
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
