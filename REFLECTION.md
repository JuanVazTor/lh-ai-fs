# Reflection

## Architecture

I decomposed the pipeline into six named agents with narrow responsibilities: citation extraction, authority verification, quote checking, MSJ fact extraction, cross-document consistency checking, and judicial memo synthesis. The orchestrator passes Pydantic models between agents rather than raw text blobs, which makes each step easier to inspect and evaluate.

## Citation Verification Tradeoff

The authority verifier is intentionally conservative. We chose not to scrape legal websites or depend on a paid legal database, so the agent does not pretend to know every cited case. Well-known authorities like Privette and Seabright receive cautious legal treatment; obscure footnote authorities are usually marked `could_not_verify`. That is less flashy than declaring cases fake, but it is safer and better aligned with the instruction to express uncertainty instead of fabricating findings.

## Confidence Scoring

Confidence is emitted by each agent rather than by a separate scoring agent. The agent closest to the evidence is best positioned to score certainty. Direct factual contradictions across multiple provided documents receive high confidence. LLM-only legal judgments receive lower confidence unless the issue is a broad, well-known doctrinal overstatement.

## Evals

The eval harness uses a small gold set of known flaws in the supplied case file and reports precision, recall, and hallucination rate. The metrics are intentionally simple and transparent. They measure whether the pipeline catches the issues that matter here and whether it invents extra findings. They do not prove general legal-research quality because there is only one case file.

## What I Would Improve

With more time, I would add retrieval from a legal source database, quote-level source text comparison, more case files for evals, async agent execution, and stricter semantic matching in the eval harness. The frontend could also add filtering and source-snippet expansion, but I kept it simple to prioritize the backend pipeline and measurable behavior.
