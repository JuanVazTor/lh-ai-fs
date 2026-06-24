"""GroundingGate: deterministic post-filter that downgrades unsupported confident flags.

Carries no model. For every confidently-asserted flag it applies a fixed, per-type
grounding rule and downgrades any flag that fails to `could_not_verify` / `low`:

- fact_contradiction / omission : the `evidence` must appear VERBATIM in a *supporting*
  document (police report, medical records, witness statement).
- misquote                      : the quoted text must be verbatim in the MSJ AND
  contain an overstatement trigger ("never", "always", ...).
- calculation_error            : the `evidence` must be grounded in the MSJ text.
- misapplied_citation / fake_citation : never confident — no legal database, so the
  verdict is `could_not_verify` by construction.
"""

from __future__ import annotations

import re

from agents.state import Flag, PipelineState

CONFIDENT_VERDICTS = {"contradicted", "unsupported"}
CONFIDENT_LEVELS = {"high", "medium"}

# Absolute terms that signal an overstated legal rule; a confident misquote needs one.
OVERSTATEMENT_TERMS = (
    "never", "always", "in all cases", "under no circumstances", "in every case",
    "cannot ever", "no exception", "without exception", "categorically", "absolutely",
)

_WS = re.compile(r"\s+")
_SENT = re.compile(r"(?<=[.!?])\s+")


def _norm(text: str) -> str:
    """Lowercase, normalize curly quotes/dashes, collapse whitespace, strip wrapping quotes."""
    text = text.lower()
    for a, b in (("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'"),
                 ("—", "-"), ("–", "-")):
        text = text.replace(a, b)
    text = _WS.sub(" ", text).strip()
    return text.strip('"').strip("'").strip()


def _chunks(evidence: str) -> list[str]:
    """Substantial sentence-sized pieces of the evidence, for verbatim substring matching."""
    parts = [p for p in _SENT.split(evidence) if len(_norm(p)) >= 30]
    if parts:
        return parts
    return [evidence] if evidence.strip() else []


def _grounded_in(evidence: str, corpus: str) -> bool:
    if not evidence.strip():
        return False
    corpus_n = _norm(corpus)
    return any(_norm(c) in corpus_n for c in _chunks(evidence))


def _downgrade(flag: Flag, reason: str) -> None:
    flag.verdict = "could_not_verify"
    flag.confidence = "low"
    note = f"[grounding-gate] downgraded — {reason}"
    flag.confidence_reasoning = f"{flag.confidence_reasoning} {note}".strip()


def apply_grounding_gate(state: PipelineState) -> dict:
    """Node: downgrade every confident flag that isn't verbatim-grounded per its type."""
    supporting = "\n\n".join(state.supporting_documents().values())
    msj = state.msj

    for flag in state.flags:
        confident = flag.verdict in CONFIDENT_VERDICTS and flag.confidence in CONFIDENT_LEVELS
        if not confident:
            continue

        if flag.type in {"misapplied_citation", "fake_citation"}:
            _downgrade(flag, "no legal database to confirm or deny an authority claim")
        elif flag.type == "misquote":
            quote = flag.evidence or flag.claim_in_msj
            has_trigger = any(term in _norm(quote) for term in OVERSTATEMENT_TERMS)
            if not (has_trigger and _grounded_in(quote, msj)):
                _downgrade(flag, "misquote lacks a verbatim overstatement trigger in the MSJ")
        elif flag.type == "calculation_error":
            if not _grounded_in(flag.evidence, msj):
                _downgrade(flag, "calculation not grounded in the MSJ text")
        else:  # fact_contradiction, omission
            if not _grounded_in(flag.evidence, supporting):
                _downgrade(flag, "no verbatim contradicting passage in a supporting document")

    return {"flags": state.flags}
