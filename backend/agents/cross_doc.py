"""CrossDocChecker: compares MSJ factual claims against the supporting documents."""

from pydantic import BaseModel

from agents.prompts import CROSS_DOC_CHECKER
from agents.state import Flag, PipelineState
from llm import call_llm_structured


class _CrossDocResult(BaseModel):
    flags: list[Flag]


def check_cross_document(state: PipelineState) -> dict:
    """Node: find MSJ facts contradicted/unsupported by police, medical, witness docs."""
    sources = "\n\n".join(
        f"===== {name.upper()} =====\n{text}"
        for name, text in state.supporting_documents().items()
    )
    user = (
        f"MOTION FOR SUMMARY JUDGMENT (claims to scrutinize):\n\n{state.msj}\n\n\n"
        f"SOURCE DOCUMENTS (ground truth to check against):\n\n{sources}"
    )
    result = call_llm_structured(
        messages=[
            {"role": "system", "content": CROSS_DOC_CHECKER},
            {"role": "user", "content": user},
        ],
        schema=_CrossDocResult,
    )
    for f in result.flags:
        f.source_agent = "CrossDocChecker"
    return {"flags": state.flags + result.flags}
