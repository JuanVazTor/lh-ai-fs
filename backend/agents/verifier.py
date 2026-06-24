"""CitationVerifier: per-citation check for misquotes and misapplied authority.

Runs once per citation (fan-out) so each authority gets focused scrutiny and one
malformed citation can't poison the analysis of the others.
"""

from pydantic import BaseModel

from agents.prompts import CITATION_VERIFIER
from agents.state import Citation, Flag, PipelineState
from llm import call_llm_structured


class _VerificationResult(BaseModel):
    """Flags raised for a single citation (empty list if it looks sound)."""

    flags: list[Flag]


def _verify_one(citation: Citation) -> list[Flag]:
    quotes = "\n".join(f'  - "{q}"' for q in citation.quotes) or "  (none)"
    user = (
        f"CITATION: {citation.raw_text}\n"
        f"PROPOSITION THE MSJ CLAIMS IT SUPPORTS: {citation.proposition}\n"
        f"DIRECT QUOTES ATTRIBUTED TO IT:\n{quotes}"
    )
    result = call_llm_structured(
        messages=[
            {"role": "system", "content": CITATION_VERIFIER},
            {"role": "user", "content": user},
        ],
        schema=_VerificationResult,
    )
    for f in result.flags:
        f.source_agent = "CitationVerifier"
    return result.flags


def verify_citations(state: PipelineState) -> dict:
    """Node: verify each extracted citation; collect any flags. Per-citation failures
    are recorded but never abort the batch (graceful degradation)."""
    flags: list[Flag] = []
    errors: list[str] = []
    for citation in state.citations:
        try:
            flags.extend(_verify_one(citation))
        except Exception as e:  # noqa: BLE001 — one bad citation must not sink the rest
            errors.append(f"CitationVerifier failed on {citation.id}: {e}")
    return {"flags": state.flags + flags, "errors": state.errors + errors}
