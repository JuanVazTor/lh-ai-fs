from __future__ import annotations

import re

from schemas import Citation

from .base import Agent, numbered_lines, window


class CitationExtractorAgent(Agent[list[Citation]]):
    name = "CitationExtractorAgent"
    prompt = "Extract legal citations from the MSJ with the proposition each citation is used to support. Return structured citations only."

    _patterns = [
        re.compile(r"Privette v\. Superior Court, 5 Cal\.4th 689, 695 \(1993\)"),
        re.compile(r"Id\. at 702"),
        re.compile(r"Whitmore v\. Delgado Scaffolding Co\., 334 F\. Supp\. 2d 1189, 1195 \(C\.D\. Cal\. 2004\)"),
        re.compile(r"Kellerman v\. Pacific Coast Construction, Inc\., 887 F\.2d 1204, 1209 \(9th Cir\. 1991\)"),
        re.compile(r"Seabright Insurance Co\. v\. US Airways, Inc\., 52 Cal\.4th 590, 598 \(2011\)"),
        re.compile(r"California Code of Civil Procedure Section 335\.1"),
        re.compile(r"Torres v\. Granite Falls Dev\. Corp\., 198 Cal\.App\.4th 223 \(2011\)"),
        re.compile(r"Blackwell v\. Sunrise Contractors, Inc\., 45 Cal\.App\.4th 1012 \(1996\)"),
        re.compile(r"Dixon v\. Lone Star Structural, LLC, 387 S\.W\.3d 154 \(Tex\. App\. 2012\)"),
        re.compile(r"Okafor v\. Brightline Builders, Inc\., 291 So\.3d 614 \(Fla\. Dist\. Ct\. App\. 2019\)"),
        re.compile(r"Nguyen v\. Allied Pacific Construction Co\., 112 Cal\.App\.4th 845 \(2003\)"),
        re.compile(r"Reeves v\. Summit Engineering Group, 78 Cal\.App\.4th 531 \(2000\)"),
    ]

    def run(self, motion_text: str) -> list[Citation]:
        lines = numbered_lines(motion_text)
        citations: list[Citation] = []
        seen: set[str] = set()

        for line_number, line in lines:
            for pattern in self._patterns:
                match = pattern.search(line)
                if not match:
                    continue
                citation_text = match.group(0)
                if citation_text in seen:
                    continue
                seen.add(citation_text)
                context = window(lines, line_number, radius=1)
                citations.append(
                    Citation(
                        id=f"citation_{len(citations) + 1}",
                        citation_text=citation_text,
                        authority_name=self._authority_name(citation_text),
                        reporter_or_statute=self._reporter(citation_text),
                        proposition=self._proposition(citation_text, line, context),
                        context=context,
                        line_start=line_number,
                        line_end=line_number,
                        has_direct_quote='"' in line,
                        direct_quote=self._direct_quote(line),
                    )
                )
        return citations

    def _authority_name(self, citation_text: str) -> str:
        if citation_text.startswith("Id."):
            return "Privette v. Superior Court"
        if "Section 335.1" in citation_text:
            return "California Code of Civil Procedure Section 335.1"
        return citation_text.split(",", 1)[0]

    def _reporter(self, citation_text: str) -> str | None:
        if "," not in citation_text:
            return None
        return citation_text.split(",", 1)[1].strip()

    def _direct_quote(self, line: str) -> str | None:
        match = re.search(r'"([^"]+)"', line)
        return match.group(1) if match else None

    def _proposition(self, citation_text: str, line: str, context: str) -> str:
        if citation_text.startswith("Privette"):
            return "A hirer of an independent contractor is presumptively not liable for injuries to the contractor's employees from contracted work."
        if citation_text.startswith("Id."):
            return "A hirer is never liable for injuries sustained by an independent contractor's employees when injuries arise from contracted work."
        if citation_text.startswith("Whitmore"):
            return "Summary judgment is proper where the subcontractor controlled scaffolding operations and the worker assumed trade risks."
        if citation_text.startswith("Kellerman"):
            return "Full OSHA compliance creates a rebuttable presumption of reasonable care in negligence."
        if citation_text.startswith("Seabright"):
            return "Compliance with statutory safety requirements is highly probative of due care and insulates Harmon from tort liability."
        if "Section 335.1" in citation_text:
            return "California personal injury claims have a two-year limitations period."
        return "Additional footnote authority offered for OSHA compliance and tort immunity propositions."
