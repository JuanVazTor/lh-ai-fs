"""Typed state shared across the BS Detector agent pipeline.

Every agent reads from and writes to a `PipelineState`. We pass these typed
objects between nodes (never raw text blobs) so each agent has a precise,
inspectable contract for its input and output.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FlagType = Literal[
    "fake_citation",       # the cited authority likely does not exist / cannot be located
    "misquote",            # a direct quote was altered (words added/removed/changed)
    "fact_contradiction",  # a factual claim in the MSJ conflicts with a source document
    "misapplied_citation", # the authority exists but does not support the proposition
    "calculation_error",   # an arithmetic / date computation in the MSJ is wrong
    "omission",            # a material, legally-relevant fact or exception was left out
]

Verdict = Literal[
    "supported",        # the source/authority backs the claim
    "unsupported",      # the claim is not backed (and we are confident)
    "contradicted",     # a source document directly contradicts the claim
    "could_not_verify", # we lack the evidence to confirm or deny — honest abstention
]

Confidence = Literal["high", "medium", "low"]


class Citation(BaseModel):
    """A single legal authority cited in the Motion for Summary Judgment."""

    id: str = Field(description="Stable id, e.g. 'cite-1'")
    raw_text: str = Field(description="The citation exactly as it appears in the MSJ")
    proposition: str = Field(
        description="The legal proposition the MSJ claims this authority supports"
    )
    quotes: list[str] = Field(
        default_factory=list,
        description="Direct quotes the MSJ attributes to this authority (verbatim)",
    )


class Flag(BaseModel):
    """A single potential problem ('BS') detected in the MSJ."""

    id: str
    type: FlagType
    source_agent: str = Field(description="Which agent produced this flag")
    claim_in_msj: str = Field(description="The exact claim/text in the MSJ being challenged")
    evidence: str = Field(
        default="",
        description=(
            "Verbatim supporting text from a source document, or the internal "
            "inconsistency. Empty only when verdict is 'could_not_verify'."
        ),
    )
    source_document: str = Field(
        default="",
        description="Which document the evidence came from (e.g. 'police_report')",
    )
    verdict: Verdict
    confidence: Confidence = "medium"
    confidence_reasoning: str = Field(
        default="",
        description="Why this confidence level — what would raise or lower it",
    )


class PipelineState(BaseModel):
    """The single object threaded through every node of the pipeline."""

    documents: dict[str, str] = Field(default_factory=dict)
    citations: list[Citation] = Field(default_factory=list)
    flags: list[Flag] = Field(default_factory=list)
    judicial_memo: str = ""
    errors: list[str] = Field(
        default_factory=list,
        description="Node-level failures recorded for graceful degradation",
    )

    @property
    def msj(self) -> str:
        """The Motion for Summary Judgment text (the document under scrutiny)."""
        return self.documents.get("motion_for_summary_judgment", "")

    def supporting_documents(self) -> dict[str, str]:
        """All documents except the MSJ — the ground truth to check facts against."""
        return {
            name: text
            for name, text in self.documents.items()
            if name != "motion_for_summary_judgment"
        }
