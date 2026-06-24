"""BS Detector pipeline orchestration.

A LangGraph StateGraph threads a single typed `PipelineState` through five LLM agents
and two deterministic (no-LLM) gate nodes:

    extract -> verify -> cross_doc -> score -> calc -> grounding -> memo

`calc` and `grounding` carry no model: `calc` runs after the scorer so its
deterministic high-confidence flag isn't re-rated down, and `grounding` runs last
(before `memo`) to downgrade any confident flag that isn't verbatim-grounded.

LangGraph gives us an explicit, inspectable graph and a clean place to wrap each
node for graceful failure handling. If LangGraph is unavailable, we fall back to a
plain sequential runner over the same node functions — the nodes don't care which
orchestrator drives them, because they all speak `PipelineState`.
"""

from __future__ import annotations

from typing import Callable

from agents.calculator import check_calculations
from agents.confidence import score_confidence
from agents.cross_doc import check_cross_document
from agents.extractor import extract_citations
from agents.grounding import apply_grounding_gate
from agents.memo import write_judicial_memo
from agents.state import PipelineState
from agents.verifier import verify_citations

# Ordered nodes: (name, function). Each returns a partial state update (a dict).
NODES: list[tuple[str, Callable[[PipelineState], dict]]] = [
    ("extract", extract_citations),
    ("verify", verify_citations),
    ("cross_doc", check_cross_document),
    ("score", score_confidence),
    ("calc", check_calculations),
    ("grounding", apply_grounding_gate),
    ("memo", write_judicial_memo),
]


def _safe(name: str, fn: Callable[[PipelineState], dict]) -> Callable[[PipelineState], dict]:
    """Wrap a node so an unhandled failure is recorded, not fatal.

    A failed node returns only an error append; downstream nodes still run with
    whatever partial results exist (e.g. cross-doc flags survive if extraction dies).
    """

    def wrapped(state: PipelineState) -> dict:
        try:
            return fn(state)
        except Exception as e:  # noqa: BLE001
            return {"errors": state.errors + [f"{name} failed: {e}"]}

    return wrapped


def _build_langgraph():
    """Build a LangGraph StateGraph, or return None if LangGraph isn't installed."""
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return None

    graph = StateGraph(PipelineState)
    for name, fn in NODES:
        graph.add_node(name, _safe(name, fn))
    graph.add_edge(START, NODES[0][0])
    for (prev, _), (nxt, _) in zip(NODES, NODES[1:]):
        graph.add_edge(prev, nxt)
    graph.add_edge(NODES[-1][0], END)
    return graph.compile()


_COMPILED = _build_langgraph()


def _run_sequential(state: PipelineState) -> PipelineState:
    """Fallback orchestrator: apply each node's partial update in order."""
    for name, fn in NODES:
        update = _safe(name, fn)(state)
        state = state.model_copy(update=update)
    return state


def run_pipeline(documents: dict[str, str]) -> PipelineState:
    """Entry point: analyze a case file and return the full verification state."""
    initial = PipelineState(documents=documents)
    if _COMPILED is not None:
        result = _COMPILED.invoke(initial)
        # LangGraph returns a dict-like; normalize back to our typed model.
        return PipelineState.model_validate(result)
    return _run_sequential(initial)
