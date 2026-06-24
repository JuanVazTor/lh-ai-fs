# BS Detector — Eval Findings

_Generated 2026-06-24 19:55 UTC from 5 live pipeline runs (temperature=0). gpt-4o._

This report goes beyond the three headline metrics to surface the error indicators that a single run hides: run-to-run variance, where over-flagging originates, whether confidence is calibrated, and how the pipeline behaves on claims it cannot verify.

> The numbers below reflect the pipeline **after** two deterministic fixes (see §0), with the before → after comparison in that section.

## 0. What changed (before → after)

Two **deterministic, no-LLM** nodes were added to the graph (`extract → verify → cross_doc → score → calc → grounding → memo`):

1. **GroundingGate** (`agents/grounding.py`) — a post-filter that downgrades any *confidently asserted* flag to `could_not_verify`/`low` unless it is verbatim-grounded by type: fact flags need a verbatim passage from a **supporting** document; a `misquote` needs a verbatim overstatement trigger ("never"/"always"…) in the MSJ; `misapplied_citation`/`fake_citation` can **never** be confident (no legal database). This kills the speculative citation flags and, being deterministic, removes most of the run-to-run variance.
2. **Calculator** (`agents/calculator.py`) — computes the statute-of-limitations day count in Python from the dates the MSJ states, so the "one year and 362 days" error (gt-5) is caught **every** run instead of 1-in-5.

| Metric (5 runs) | Before | After |
|---|---|---|
| Precision | 46% ±4% | **77% ±11%** |
| Recall | 84% ±8% | **100% ±0%** |
| Hallucination | 46% ±5% | **12% ±6%** |
| F1 | 59% ±5% | **87% ±7%** |
| gt-5 (date math) caught | 1/5 | **5/5** |
| CitationVerifier precision | 17% | **100%** (speculative flags now abstain) |

**Residual (next levers, unchanged here):** the remaining false positives are now concentrated in `CrossDocChecker` (≈65% precision) and are mostly **legal conclusions** mislabeled as factual contradictions (§5) — addressable with a legal-conclusion gate — plus a near-duplicate of the date/calc flaw (de-duplication). Two fabricated-looking citations (gt-6, gt-7) are still **silently dropped** rather than explicitly abstained on (§6).

## 1. Metric distribution

| Metric | mean | std | min | max |
|---|---|---|---|---|
| Precision | 77% | ±11% | 71% | 100% |
| Recall | 100% | ±0% | 100% | 100% |
| Hallucination | 12% | ±6% | 0% | 15% |
| F1 | 87% | ±7% | 83% | 100% |

**Indicator:** even at `temperature=0` the metrics move between runs — the spread above is itself a reliability finding, not noise to hide.

## 2. Flaw stability (caught in how many of 5 runs)

| Flaw | caught | summary |
|---|---|---|
| gt-1 | 5/5 | Incident date is March 14, 2021 in the MSJ but March 12, 2021 in the police report, medica |
| gt-2 | 5/5 | MSJ claims Rivera was not wearing required PPE / fall-arrest equipment. Police report and  |
| gt-3 | 5/5 | MSJ quotes Privette as 'A hirer is never liable for injuries sustained by an independent c |
| gt-4 | 5/5 | MSJ invokes Privette but omits the retained-control exception. The record shows Harmon's f |
| gt-5 | 5/5 | MSJ states the filing was 'one year and 362 days' after the incident. The day count is wro |

**Indicator:** consistently missed: none; flaky (run-dependent): none.

## 3. Per-agent precision (source of over-flagging, summed over 5 runs)

| Agent | TP | FP | hedged | precision |
|---|---|---|---|---|
| Calculator | 5 | 0 | 0 | 100% |
| CitationVerifier | 5 | 0 | 30 | 100% |
| CrossDocChecker | 15 | 8 | 1 | 65% |

## 4. Confidence calibration (summed over 5 runs)

| Level | TP | FP | hedged | accuracy |
|---|---|---|---|---|
| high | 15 | 2 | 0 | 88% |
| medium | 6 | 6 | 0 | 50% |
| low | 4 | 0 | 31 | 100% |

**Indicator:** if `high` accuracy exceeds `medium`, the confidence signal is usable as a triage gate (auto-surface high, route medium to human review).

## 5. Fact vs. legal conclusion (characterizing the false positives)

6 of 8 false positives (across 5 runs) are *legal conclusions* mislabeled as factual contradictions. Examples:

- **[fact_contradiction/medium]** Harmon maintained an active Injury and Illness Prevention Program ("IIPP") and had passed all OSHA inspections conducted at the site during the relevant period, the most recent being February 26, 2021.
  - evidence offered: _Tran further stated that she and other crew members had raised concerns about the condition of the east-side scaffolding earlier in the week, noting that some of the cross-braces "didn't look right" a_
- **[fact_contradiction/medium]** Rivera assumed the risk inherent in his trade.
  - evidence offered: _I raised these concerns with our crew lead, Mark Ellison, before we began work. Mark told me he would "take a look," but I did not see him inspect the section. I also mentioned the base plate issue di_

**Indicator:** legal-conclusion mislabeling is a *minor* contributor (6/8). The dominant source of false positives is **CrossDocChecker** (8 FPs, 65% precision) — it confidently asserts citation problems it cannot actually verify. The biggest precision lever is forcing that agent to abstain (`could_not_verify`) instead of guessing, not a legal-conclusion gate.

## 6. Abstention behavior (non-verifiable flaws)

1/3 non-verifiable flaws were *explicitly* marked `could_not_verify`; **2 were silently dropped** (gt-6, gt-7).

**Indicator:** silent omission and honest abstention look identical to a user. The pipeline should emit an explicit `could_not_verify` for suspect citations (Whitmore, Kellerman, Seabright) instead of producing nothing.

## 7. Node errors

0 node failures across 5 runs (graceful-degradation wrapper recorded them in `state.errors`).

