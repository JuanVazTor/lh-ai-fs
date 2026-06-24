"""CitationExtractor: pulls every legal authority + attributed quote from the MSJ."""

from pydantic import BaseModel

from agents.prompts import CITATION_EXTRACTOR
from agents.state import Citation, PipelineState
from llm import call_llm_structured


class _ExtractionResult(BaseModel):
    """Wrapper schema — OpenAI structured outputs need an object at the top level."""

    citations: list[Citation]


def extract_citations(state: PipelineState) -> dict:
    """Node: read the MSJ, return all citations with propositions and quotes."""
    result = call_llm_structured(
        messages=[
            {"role": "system", "content": CITATION_EXTRACTOR},
            {"role": "user", "content": f"MOTION FOR SUMMARY JUDGMENT:\n\n{state.msj}"},
        ],
        schema=_ExtractionResult,
    )
    # Ensure stable ids regardless of what the model emitted.
    citations = []
    for i, c in enumerate(result.citations, start=1):
        c.id = f"cite-{i}"
        citations.append(c)
    return {"citations": citations}
