"""Calculator: deterministic date arithmetic for elapsed-time claims (no LLM).

Scans the MSJ for any "<N> year(s) and <N> days" / "<N> days" assertion that sits in a
sentence with an elapsed-time cue, pairs it with the two dates in its local context,
and flags it when the asserted interval disagrees with the computed one. Abstains
(emits nothing) when it cannot pair the assertion with two dates.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from agents.state import Flag, PipelineState

# Small cardinal words that can precede "years".
_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
_NUM = r"\d+|" + "|".join(sorted(_WORDS, key=len, reverse=True))

_DURATION = re.compile(
    rf"\b(?P<years>{_NUM})\s+years?\s*,?\s+and\s+(?P<days>\d+)\s+days\b", re.IGNORECASE
)
_DAYS_ONLY = re.compile(r"\b(?P<days>\d+)\s+days\b", re.IGNORECASE)

_LONG_DATE = re.compile(r"\b[A-Z][a-z]+ \d{1,2}, \d{4}\b")
_NUM_DATE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")

# Cue words that mark a sentence as stating an elapsed interval (not a statute period).
_ELAPSED_CUES = ("after", "later", "elapsed", "between", "from", "until", "filed", "within")

_SENT_END = re.compile(r"[.!?](?:\s|$)")


def _to_int(token: str) -> int:
    token = token.lower()
    return int(token) if token.isdigit() else _WORDS[token]


def _parse_date(s: str) -> date | None:
    for fmt in ("%B %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _dates_in(text: str) -> list[date]:
    found = [_parse_date(s) for s in _LONG_DATE.findall(text) + _NUM_DATE.findall(text)]
    return [d for d in found if d]


def _years_and_days(d0: date, d1: date) -> tuple[int, int]:
    """Whole years between d0 and d1, plus leftover days (calendar-correct)."""
    years = d1.year - d0.year

    def anniversary(y: int) -> date:
        try:
            return d0.replace(year=d0.year + y)
        except ValueError:  # Feb 29 -> Feb 28 in non-leap years
            return d0.replace(year=d0.year + y, day=28)

    if anniversary(years) > d1:
        years -= 1
    return years, (d1 - anniversary(years)).days


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for m in _SENT_END.finditer(text):
        spans.append((start, m.end()))
        start = m.end()
    if start < len(text):
        spans.append((start, len(text)))
    return spans


def _context(text: str, spans: list[tuple[int, int]], pos: int) -> tuple[str, str]:
    """Return (claim_sentence, window) — the sentence holding `pos`, and that sentence
    plus the previous one. Both are verbatim slices of the MSJ."""
    i = next((k for k, (s, e) in enumerate(spans) if s <= pos < e), len(spans) - 1)
    win_start = spans[i - 1][0] if i > 0 else spans[i][0]
    return text[spans[i][0]:spans[i][1]].strip(), text[win_start:spans[i][1]].strip()


def _evaluate(msj: str, spans, span, expected_years: int, expected_days: int) -> Flag | None:
    claim, window = _context(msj, spans, span[0])
    if not any(cue in window.lower() for cue in _ELAPSED_CUES):
        return None
    dates = sorted(set(_dates_in(window)))
    if len(dates) < 2:
        return None  # can't confidently pair the assertion with an interval — abstain

    d0, d1 = dates[0], dates[-1]
    years, days = _years_and_days(d0, d1)
    if expected_years == 0:  # the assertion was a bare day count
        actual_total, asserted_total = (d1 - d0).days, expected_days
        if actual_total == asserted_total:
            return None
        actual_str, asserted_str = f"{actual_total} days", f"{asserted_total} days"
    else:
        if (years, days) == (expected_years, expected_days):
            return None
        actual_str = f"{years} year(s) and {days} days"
        asserted_str = f"{expected_years} year(s) and {expected_days} days"

    return Flag(
        id="",  # assigned by the caller
        type="calculation_error",
        source_agent="Calculator",
        claim_in_msj=claim,
        evidence=window,
        source_document="motion_for_summary_judgment",
        verdict="unsupported",
        confidence="high",
        confidence_reasoning=(
            f"Deterministic date arithmetic: {d0.strftime('%B %d, %Y')} to "
            f"{d1.strftime('%B %d, %Y')} is {actual_str}, not the {asserted_str} asserted."
        ),
    )


def check_calculations(state: PipelineState) -> dict:
    """Node: verify every elapsed-time assertion in the MSJ against the dates it cites."""
    msj = state.msj
    if not msj:
        return {}

    spans = _sentence_spans(msj)
    flags: list[Flag] = []
    consumed: list[tuple[int, int]] = []

    for m in _DURATION.finditer(msj):
        consumed.append(m.span())
        flag = _evaluate(msj, spans, m.span(), _to_int(m.group("years")), int(m.group("days")))
        if flag:
            flags.append(flag)

    for m in _DAYS_ONLY.finditer(msj):
        if any(s <= m.start() < e for s, e in consumed):  # already inside a "years and days" match
            continue
        flag = _evaluate(msj, spans, m.span(), 0, int(m.group("days")))
        if flag:
            flags.append(flag)

    if not flags:
        return {}
    for i, flag in enumerate(flags, start=1):
        flag.id = f"calc-{i}"
    return {"flags": state.flags + flags}
