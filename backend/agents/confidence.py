"""ConfidenceScorer: assigns a calibrated confidence + reasoning to each flag."""

from pydantic import BaseModel

from agents.prompts import CONFIDENCE_SCORER
from agents.state import Flag, PipelineState
from llm import call_llm_structured


class _ScoringResult(BaseModel):
    flags: list[Flag]


def score_confidence(state: PipelineState) -> dict:
    """Node: re-rate every flag's confidence. No flags are added or removed.

    If scoring fails, we keep the upstream flags (with their default confidence)
    rather than losing the analysis entirely.
    """
    if not state.flags:
        return {}

    flags_json = "\n".join(
        f"{i}. [{f.type}] claim={f.claim_in_msj!r} verdict={f.verdict} "
        f"evidence={f.evidence!r}"
        for i, f in enumerate(state.flags, start=1)
    )
    try:
        result = call_llm_structured(
            messages=[
                {"role": "system", "content": CONFIDENCE_SCORER},
                {"role": "user", "content": f"FLAGS TO SCORE:\n{flags_json}"},
            ],
            schema=_ScoringResult,
        )
    except Exception as e:  # noqa: BLE001
        return {"errors": state.errors + [f"ConfidenceScorer failed: {e}"]}

    # Merge scores back by position when counts line up; otherwise keep originals.
    if len(result.flags) == len(state.flags):
        merged: list[Flag] = []
        for original, scored in zip(state.flags, result.flags):
            original.confidence = scored.confidence
            original.confidence_reasoning = scored.confidence_reasoning
            merged.append(original)
        return {"flags": merged}
    return {"errors": state.errors + ["ConfidenceScorer count mismatch; kept originals"]}
