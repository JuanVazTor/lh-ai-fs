# Reflection

## Architecture

I decomposed the pipeline into six named agents with narrow responsibilities: citation extraction, authority verification, quote checking, MSJ fact extraction, cross-document consistency checking, and judicial memo synthesis. The orchestrator passes Pydantic models between agents rather than raw text blobs, which makes each step easier to inspect and evaluate.

The pipeline is intentionally LLM-driven because this repository is meant to evaluate an LLM implementation. Extraction, authority verification, quote checking, fact consistency analysis, and judicial memo synthesis all call the model and validate structured outputs where applicable. If `OPENAI_API_KEY` is missing or a response fails schema validation, the affected agent records an error rather than substituting deterministic fallback behavior.

## Citation Verification Tradeoff

The authority verifier is intentionally conservative. We chose not to scrape legal websites or depend on a paid legal database, so the agent does not pretend to know every cited case. Well-known authorities like Privette and Seabright receive cautious legal treatment; obscure footnote authorities are usually marked `could_not_verify`. That is less flashy than declaring cases fake, but it is safer and better aligned with the instruction to express uncertainty instead of fabricating findings.

## Confidence Scoring

Confidence is emitted by each agent rather than by a separate scoring agent. The agent closest to the evidence is best positioned to score certainty. Direct factual contradictions across multiple provided documents receive high confidence. LLM-only legal judgments receive lower confidence unless the issue is a broad, well-known doctrinal overstatement.

## Evals

The eval harness uses a small gold set of known flaws in the supplied case file and reports precision, recall, hallucination rate, grounding, uncertainty behavior, mutation sensitivity, and adversarial mini-case performance. The adversarial cases include a clean brief that should not produce contradiction flags and an obvious fabricated citation that should be detected. These metrics are more honest than a single perfect score, but they still do not prove general legal-research quality because the corpus is small.

The first LLM-only eval run exposed an important scoring limitation: the model identified real date and PPE issues, but generated different flag IDs than the gold set. I updated the harness to match findings by meaning, evidence, status compatibility, and confidence rather than exact IDs. Weak matches are now reported separately, and hallucination means an unsupported issue rather than an unexpected identifier.

## What I Would Improve

With more time, I would add retrieval from a legal source database, quote-level source text comparison, more case files for evals, async agent execution, and an LLM-as-judge scorer for borderline semantic matches. The frontend could also add filtering and source-snippet expansion, but I kept it simple to prioritize the backend pipeline and measurable behavior.
