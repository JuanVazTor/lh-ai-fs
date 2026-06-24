"""JudicialMemo: synthesizes the top findings into one paragraph for the judge."""

from agents.prompts import JUDICIAL_MEMO
from agents.state import PipelineState
from llm import call_llm


def write_judicial_memo(state: PipelineState) -> dict:
    """Node: produce a one-paragraph, judge-facing summary of the findings."""
    if not state.flags:
        return {
            "judicial_memo": (
                "The verification pipeline identified no problems in the Motion "
                "for Summary Judgment that could be confirmed against the record."
            )
        }

    findings = "\n".join(
        f"- [{f.type}, confidence={f.confidence}, verdict={f.verdict}] "
        f"{f.claim_in_msj} | evidence: {f.evidence or '(none)'}"
        for f in state.flags
    )
    try:
        memo = call_llm(
            messages=[
                {"role": "system", "content": JUDICIAL_MEMO},
                {"role": "user", "content": f"SCORED FINDINGS:\n{findings}"},
            ],
        )
    except Exception as e:  # noqa: BLE001
        return {
            "judicial_memo": "",
            "errors": state.errors + [f"JudicialMemo failed: {e}"],
        }
    return {"judicial_memo": memo.strip()}
