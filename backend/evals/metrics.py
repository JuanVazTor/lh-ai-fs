"""Matching + metric computation for the BS Detector eval harness.

Design choices (defend these in the interview):

- We match a produced flag to a ground-truth flaw using a transparent, deterministic
  rule: same flaw *family* (we group the six flag types into 3 families so a
  "misquote" can satisfy an "unsupported quote" flaw, etc.) AND keyword overlap
  between the flag text and the flaw's curated keywords. No LLM judge in the loop —
  the scoring itself must be trustworthy and reproducible, not another model that
  can hallucinate.

- Recall is measured ONLY over flaws we expect a text-only pipeline to catch
  (verifiable == true). Asking the pipeline to "catch" a fabricated citation it
  cannot confirm would reward guessing. Those non-verifiable flaws are instead used
  to measure honesty (see hallucination_rate).

- Hallucination = a confidently-asserted flag (verdict in {contradicted, unsupported}
  with confidence in {high, medium}) that matches NO ground-truth flaw. A
  "could_not_verify" output is never a hallucination — abstention is honest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Group flag types into families so related labels (e.g. misquote/misapplied) can match.
TYPE_FAMILY = {
    "fact_contradiction": "fact",
    "omission": "fact",
    "calculation_error": "fact",
    "misquote": "authority",
    "misapplied_citation": "authority",
    "fake_citation": "authority",
}

CONFIDENT_VERDICTS = {"contradicted", "unsupported"}
CONFIDENT_LEVELS = {"high", "medium"}

# Phrases that mark a flag's claim as a legal conclusion rather than a checkable fact
# (e.g. "Rivera assumed the risk", "maintained an IIPP"). See is_legal_conclusion().
LEGAL_CONCLUSION_MARKERS = (
    "assumed the risk",
    "barred by",
    "liable",
    "doctrine",
    "presumption",
    "rebuttable",
    "standard of care",
    "iipp",
    "injury and illness prevention",
    "passed all osha",
    "due care",
    "summary judgment",
)

_WORD = re.compile(r"[a-z0-9.]+")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _flag_text(flag: dict) -> str:
    return " ".join(
        str(flag.get(k, "")) for k in ("type", "claim_in_msj", "evidence", "confidence_reasoning")
    )


def is_legal_conclusion(flag: dict) -> bool:
    """True if the flag's claim contains a known legal-conclusion phrase."""
    claim = str(flag.get("claim_in_msj", "")).lower()
    return any(marker in claim for marker in LEGAL_CONCLUSION_MARKERS)


def _match_score(flag: dict, flaw: dict) -> int:
    """How strongly a flag matches a flaw: number of curated keyword phrases that
    appear in full. Returns 0 (no match) unless the type families align.

    We score rather than return a bool so that when one flag could superficially
    touch several flaws (a generic word like "incident"), it is assigned to the flaw
    it overlaps with most — not merely the first one in file order."""
    if TYPE_FAMILY.get(flag.get("type")) != TYPE_FAMILY.get(flaw["type"]):
        return 0
    text_tokens = _tokens(_flag_text(flag))
    return sum(
        1
        for kw in flaw["match_keywords"]
        if (kw_tokens := _tokens(kw)) and kw_tokens <= text_tokens
    )


@dataclass
class EvalResult:
    matched_flaw_ids: set[str] = field(default_factory=set)
    verifiable_flaw_ids: set[str] = field(default_factory=set)
    caught_verifiable_ids: set[str] = field(default_factory=set)
    true_positive_flags: list[dict] = field(default_factory=list)
    hallucinated_flags: list[dict] = field(default_factory=list)
    unmatched_flags: list[dict] = field(default_factory=list)  # not confident enough to be hallucinations

    @property
    def precision(self) -> float:
        confident = len(self.true_positive_flags) + len(self.hallucinated_flags)
        if confident == 0:
            return 1.0
        return len(self.true_positive_flags) / confident

    @property
    def recall(self) -> float:
        if not self.verifiable_flaw_ids:
            return 1.0
        return len(self.caught_verifiable_ids) / len(self.verifiable_flaw_ids)

    @property
    def hallucination_rate(self) -> float:
        total_flags = (
            len(self.true_positive_flags)
            + len(self.hallucinated_flags)
            + len(self.unmatched_flags)
        )
        if total_flags == 0:
            return 0.0
        return len(self.hallucinated_flags) / total_flags

    @property
    def f1(self) -> float:
        """Harmonic mean of precision and recall — one quality number."""
        p, r = self.precision, self.recall
        if p + r == 0:
            return 0.0
        return 2 * p * r / (p + r)


def evaluate(flags: list[dict], ground_truth: dict) -> EvalResult:
    """Score a pipeline run's flags against the ground-truth flaws.

    Matching is a one-to-one greedy assignment: we rank every (flag, flaw) pair by
    keyword-overlap score and assign strongest pairs first, so each flaw is credited
    at most once and each flag matches at most one flaw. This prevents one strong
    flag from soaking up credit for several flaws (or vice versa)."""
    flaws = ground_truth["flaws"]
    result = EvalResult(
        verifiable_flaw_ids={f["id"] for f in flaws if f["verifiable"]},
    )

    pairs = sorted(
        (
            (_match_score(flag, flaw), fi, flaw)
            for fi, flag in enumerate(flags)
            for flaw in flaws
        ),
        key=lambda p: p[0],
        reverse=True,
    )
    flag_of_flaw: dict[int, dict] = {}  # flag index -> flaw it was assigned to
    used_flaws: set[str] = set()
    for score, fi, flaw in pairs:
        if score == 0:
            break
        if fi in flag_of_flaw or flaw["id"] in used_flaws:
            continue
        flag_of_flaw[fi] = flaw
        used_flaws.add(flaw["id"])

    for fi, flag in enumerate(flags):
        hit = flag_of_flaw.get(fi)
        is_confident = (
            flag.get("verdict") in CONFIDENT_VERDICTS
            and flag.get("confidence") in CONFIDENT_LEVELS
        )
        if hit:
            result.matched_flaw_ids.add(hit["id"])
            if hit["verifiable"]:
                result.caught_verifiable_ids.add(hit["id"])
            result.true_positive_flags.append(flag)
        elif is_confident:
            # Confidently asserted something that matches no known flaw = fabricated.
            result.hallucinated_flags.append(flag)
        else:
            # Unmatched but hedged (e.g. could_not_verify) — neither credited nor punished.
            result.unmatched_flags.append(flag)

    return result


def agent_breakdown(result: EvalResult) -> dict[str, dict]:
    """Per-agent TP / FP / precision.

    A flag is a true positive if it matched a flaw, a false positive if it was a
    confident hallucination. Hedged/unmatched flags are counted but don't hurt precision."""
    stats: dict[str, dict] = {}

    def _bucket(agent: str) -> dict:
        return stats.setdefault(agent, {"tp": 0, "fp": 0, "hedged": 0})

    for f in result.true_positive_flags:
        _bucket(f.get("source_agent", "?"))["tp"] += 1
    for f in result.hallucinated_flags:
        _bucket(f.get("source_agent", "?"))["fp"] += 1
    for f in result.unmatched_flags:
        _bucket(f.get("source_agent", "?"))["hedged"] += 1

    for agent, s in stats.items():
        confident = s["tp"] + s["fp"]
        s["total"] = s["tp"] + s["fp"] + s["hedged"]
        s["precision"] = s["tp"] / confident if confident else 1.0
    return stats


def confidence_breakdown(result: EvalResult) -> dict[str, dict]:
    """Per-confidence-level accuracy = TP / (TP + FP) among confident flags at that level.

    Hedged flags (could_not_verify etc.) are counted separately."""
    levels: dict[str, dict] = {}

    def _bucket(level: str) -> dict:
        return levels.setdefault(level, {"tp": 0, "fp": 0, "hedged": 0})

    for f in result.true_positive_flags:
        _bucket(f.get("confidence", "?"))["tp"] += 1
    for f in result.hallucinated_flags:
        _bucket(f.get("confidence", "?"))["fp"] += 1
    for f in result.unmatched_flags:
        _bucket(f.get("confidence", "?"))["hedged"] += 1

    for level, s in levels.items():
        confident = s["tp"] + s["fp"]
        s["accuracy"] = s["tp"] / confident if confident else None
    return levels
