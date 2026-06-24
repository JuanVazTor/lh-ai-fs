# Reflection

## What I built

A pipeline that verifies a Motion for Summary Judgment against its case file, plus an
eval harness that scores it honestly. Five LLM agents are deliberately narrow:
extraction, citation verification, cross-document fact-checking, confidence scoring,
and a judicial memo. Two later nodes are **deterministic** (no LLM): a `Calculator`
that does the statute-of-limitations date math, and a `GroundingGate` that downgrades
any confidently-asserted flag that isn't verbatim-grounded. State is a single typed
Pydantic object passed between nodes by a LangGraph `StateGraph`; no node sees
another's raw text output.

The two deterministic nodes were not in my first version — I added them *after* the
eval surfaced where the pipeline was actually failing (see the numbers below).

## How I decomposed the problem

The core insight is that "BS" in a brief comes in two different shapes, and they need
different evidence to catch:

1. **Authority problems** (fabricated cases, altered quotes, stretched holdings) —
   these live *inside* the brief and the cited law. The pipeline has no legal
   database, so for these the honest default is often "could not verify."
2. **Fact problems** (claims contradicted by the record) — these are *checkable*
   against the supporting documents we do have.

So I split verification into `CitationVerifier` (authority) and `CrossDocChecker`
(facts). Keeping them separate matters: the fact-checker can be confident because it
quotes a contradicting source verbatim; the citation-checker must usually hedge. A
single combined agent would blur that confidence boundary, which is exactly where
hallucination hides.

`ConfidenceScorer` runs after the two verification agents so it scores the full set of
flags at once rather than in isolation, and `JudicialMemo` runs at the very end so it
synthesizes over the final, gated flags.

## The eval approach

The metric design encodes a point of view about what "good" means for this product:

- **Recall is measured only over text-verifiable flaws.** Three of the eight
  ground-truth flaws (two likely-fabricated citations, one stretched holding) cannot
  be confirmed without Westlaw. Rewarding the pipeline for "catching" them would
  reward confident guessing — the opposite of what a legal tool should do. Those
  flaws instead feed the honesty check.
- **Hallucination = confident + wrong.** A flag only counts as a hallucination if it
  asserts a contradiction/unsupported verdict at medium/high confidence *and* matches
  no real flaw. A `could_not_verify` output is never punished. This makes abstention
  the safe move, which is the behavior I want from a tool lawyers would rely on.
- **Matching is deterministic, not an LLM judge.** Flags are matched to flaws by
  type-family + curated-keyword overlap, assigned one-to-one by strongest overlap. I
  deliberately avoided an LLM-as-judge for scoring: the scorer itself must be
  trustworthy and reproducible, and adding a model to grade a model just moves the
  hallucination risk into the eval.

### Latest honest numbers

Measuring over a single run hid most of what was wrong, so the harness now runs the
pipeline N times and reports the distribution plus per-agent precision and confidence
calibration (`python run_evals.py --runs 5`). Across 5 runs at `temperature=0`:

```
              before gates        after gates
Precision     46% ±4%             77% ±11%
Recall        84% ±8%             100% ±0%
Hallucination 46% ±5%             12% ±6%
F1            59% ±5%             87% ±7%
```

The **single-run snapshot I first reported (67/80/33) was not representative** — the
multi-run view showed precision was really ~46% and the metrics swung run to run.
Three findings drove the fix:

1. **Over-flagging traced to one agent.** Per-agent precision showed the
   `CitationVerifier` was the source of ~24 of 25 false positives — it confidently
   asserted "misapplied holding" calls it had no legal database to support. The
   `CrossDocChecker` (anchored to verbatim source passages) was fine.
2. **Confidence was calibrated but `medium` was poisoned.** `high`-confidence flags
   were ~100% correct; `medium` was ~19%, because the speculative citation flags all
   landed there.
3. **The date error was flaky, not a clean miss.** "One year and 362 days" was caught
   1 run in 5 — LLMs are unreliable at arithmetic.

The two deterministic gates target exactly these: the `GroundingGate` forces
unverifiable citation flags to abstain (`could_not_verify`), and the `Calculator`
computes the day count in Python so gt-5 is caught every run. Because they are
deterministic, recall variance dropped to zero. The residual false positives are now
in the `CrossDocChecker` and are mostly *legal conclusions* mislabeled as factual
contradictions — the next lever, not yet pulled. Full breakdown in
[`docs/eval-findings.md`](docs/eval-findings.md).

## Tradeoffs I made

- **LangGraph over hand-rolled orchestration.** It gave me an explicit graph and a
  clean per-node failure wrapper, and it's a credible production starting point. Cost:
  a dependency and some ceremony for what is currently a linear chain. I kept a plain
  sequential fallback so the agents don't depend on the orchestrator.
- **Fan-out per citation in the verifier.** More API calls and latency, but each
  authority gets focused scrutiny and one malformed citation can't poison the rest.
- **Prompts centralized in one file.** Optimized for reviewer inspectability (a stated
  evaluation criterion) over co-locating each prompt with its agent.
- **Structured outputs via the OpenAI parse API.** Buys schema-valid JSON for free;
  ties the pipeline to OpenAI's structured-output support.
- **Determinism over prompt-tuning for the known failure modes.** Faced with the
  over-flagging and the flaky date math, I added deterministic gate nodes rather than
  trying to coax better behavior out of a prompt. A gate decides by the *text*, not
  the model's mood on a given run — reproducible, auditable, and it drove recall
  variance to zero. The cost is that the gate encodes my rules explicitly and must be
  maintained as the document types broaden.

## What I'd do differently with more time

Two items from my first draft are now **done** (and the eval is how I knew they were
worth doing): the deterministic `Calculator` for the date error, and a grounding gate
to stop the citation over-flagging. What I'd do next:

1. **A citation-lookup tool** (CourtListener / a reporter API) would turn "could not
   verify" into real fake-citation detection — the single biggest remaining capability
   gap. Today the pipeline honestly abstains on the likely-fabricated cases.
2. **A legal-conclusion gate.** The residual false positives are in `CrossDocChecker`
   labeling legal conclusions ("assumed the risk", "maintained an IIPP") as factual
   contradictions. A gate that requires a flag's claim to be a record *fact*, not a
   conclusion, is the next cheapest precision win.
3. **Expand the eval set.** Eight flaws on one brief is enough to be honest but too
   small to be stable; multi-run variance is now reported, but I'd add clean briefs to
   measure the false-positive rate on genuinely sound filings.
4. **De-duplicate flags** across nodes and give each a stable provenance trail (one
   residual false positive is a near-duplicate of the date/calculation flaw).
5. **Make abstention explicit, not silent.** Two fabricated-looking citations are
   currently dropped silently rather than surfaced as `could_not_verify`.

## Time spent

Roughly within the prototype timebox. I lost time early to an OpenAI billing/quota
issue and a Docker gotcha (`docker compose restart` does not reload `env_file` — you
must recreate the container), neither of which is reflected in the code. I
prioritized the required deliverables (working endpoint, eval harness, this
reflection, the production plan) over the Tier 3 UI, which I treated as the first
thing to cut.
