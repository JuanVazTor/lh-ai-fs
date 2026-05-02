# Architecture

## Overview

The pipeline takes a set of legal documents (a Motion for Summary Judgment plus supporting source documents) and produces a structured verification report. It is organized as six specialized agents coordinated by an orchestrator, with Pydantic models flowing between them.

```mermaid
flowchart TD
    REQ["POST /analyze"] --> LOAD["load_documents()"]
    LOAD --> ORCH["Orchestrator"]

    ORCH --> CE["CitationExtractorAgent"]
    ORCH --> AV["AuthorityVerifierAgent"]
    ORCH --> QC["QuoteCheckerAgent"]
    ORCH --> FE["FactExtractorAgent"]
    ORCH --> CC["ConsistencyCheckerAgent"]

    CE -- "list[Citation]" --> AV
    CE -- "list[Citation]" --> QC
    FE -- "list[FactClaim]" --> CC

    ORCH --> FLAGS["Flag Builder"]
    AV -- "list[CitationVerification]" --> FLAGS
    QC -- "list[QuoteCheck]" --> FLAGS
    CC -- "list[ConsistencyFinding]" --> FLAGS

    FLAGS -- "list[VerificationFlag]" --> JM["JudicialMemoAgent"]

    JM --> REPORT["VerificationReport"]
    FLAGS --> REPORT

    REPORT --> RESP["JSON response"]

    style CE fill:#dbeafe,stroke:#1e40af
    style AV fill:#dbeafe,stroke:#1e40af
    style QC fill:#dbeafe,stroke:#1e40af
    style FE fill:#dbeafe,stroke:#1e40af
    style CC fill:#dbeafe,stroke:#1e40af
    style JM fill:#fef3c7,stroke:#92400e
    style ORCH fill:#f3e8ff,stroke:#6b21a8
    style FLAGS fill:#f3e8ff,stroke:#6b21a8
```

---

## Data Flow

All inter-agent communication uses typed Pydantic models defined in `backend/schemas.py`. No agent receives raw text blobs from another agent.

### Schema types

| Model | Purpose | Produced by | Consumed by |
|---|---|---|---|
| `Citation` | Extracted citation with proposition, quote, and context | CitationExtractor | AuthorityVerifier, QuoteChecker |
| `CitationVerification` | Whether the authority supports the proposition | AuthorityVerifier | Orchestrator (flag builder) |
| `QuoteCheck` | Whether a direct quote is accurate or overbroad | QuoteChecker | Orchestrator (flag builder) |
| `FactClaim` | Verifiable factual assertion from the MSJ | FactExtractor | ConsistencyChecker |
| `ConsistencyFinding` | Comparison of an MSJ claim against source documents | ConsistencyChecker | Orchestrator (flag builder) |
| `VerificationFlag` | Normalized finding with confidence, severity, and reasoning | Orchestrator | JudicialMemo |
| `AgentError` | Record of a failed agent run | Orchestrator | Report output |
| `VerificationReport` | Complete structured output | Orchestrator | API response |

### Status vocabulary

Every finding uses a shared status set so the eval harness can compare consistently:

| Status | Meaning |
|---|---|
| `supported` | Evidence confirms the claim |
| `partially_supported` | Evidence partially confirms but complicates the claim |
| `not_supported` | Authority or evidence does not support the proposition |
| `could_not_verify` | Insufficient information to make a determination |
| `likely_fabricated` | The cited authority appears to not exist |
| `contradicted` | Source documents directly contradict the MSJ claim |
| `not_found` | No supporting evidence found in provided documents |

---

## Agents

### 1. CitationExtractorAgent

**File:** `backend/agents/citation_extractor.py`

**Input:** Raw MSJ text

**Output:** `list[Citation]`

**Approach:** Regex-based extraction against known citation patterns in the MSJ. For each matched citation, it records the authority name, reporter citation, surrounding context, the proposition the citation supports, and any direct quote text on the same line.

**Why regex, not LLM:** Citation extraction is a structured pattern-matching task. Regex gives deterministic, reproducible results and does not require an API key. The tradeoff is that the pattern list is specific to this case file; a production system would need a more general citation parser.

**Proposition mapping:** Each recognized citation maps to a human-written proposition summarizing what the MSJ uses it to support. This keeps the authority verifier and quote checker grounded in what the brief actually argues, rather than guessing.

### 2. AuthorityVerifierAgent

**File:** `backend/agents/authority_verifier.py`

**Input:** `list[Citation]`

**Output:** `list[CitationVerification]`

**Approach:** For each citation, assesses whether the cited authority actually supports the proposition as stated. Uses a conservative LLM-only strategy: well-known authorities (Privette, Seabright, CCP 335.1) receive cautious legal analysis; obscure or unverifiable authorities receive `could_not_verify` with low confidence.

**Key design decision:** The agent does not scrape legal websites or query a legal database. This was a deliberate tradeoff to avoid rate limits, paywalls, and fragility. The downside is that the agent cannot definitively confirm or deny obscure citations. It compensates by being explicit about uncertainty and by not fabricating holdings.

**Confidence ranges:**
- Known authorities with clear support or problems: 0.67-0.90
- Obscure authorities without source text: 0.30-0.45
- Overbreadth findings on well-known doctrine: 0.78

### 3. QuoteCheckerAgent

**File:** `backend/agents/quote_checker.py`

**Input:** `list[Citation]` (filtered to those with direct quotes)

**Output:** `list[QuoteCheck]`

**Approach:** Checks direct quotes from the MSJ for accuracy or material overbreadth. The Privette "never liable" quote is flagged as overbroad because it omits recognized exceptions. All other quotes are marked `could_not_verify` because the pipeline does not have source authority text to compare against.

**Limitation:** Without retrieved case text, the agent can only flag overbreadth for well-known doctrine. It cannot verify word-for-word accuracy against the primary source.

### 4. FactExtractorAgent

**File:** `backend/agents/fact_extractor.py`

**Input:** Raw MSJ text

**Output:** `list[FactClaim]`

**Approach:** Searches for specific factual assertions in the MSJ using keyword matching. Each claim gets a stable ID, a category, and the surrounding context. This agent does not verify claims; it only identifies them for the consistency checker.

**Claims extracted:**

| ID | Claim |
|---|---|
| `incident_date` | The incident occurred on March 14, 2021 |
| `no_ppe` | Rivera was not wearing required PPE |
| `osha_compliance` | Harmon passed all OSHA inspections |
| `apex_control` | Apex, not Harmon, controlled scaffolding operations |
| `filing_date` | Rivera filed the action on March 10, 2023 |
| `limitations_elapsed` | Rivera filed one year and 362 days after the incident |
| `immediate_injury` | Rivera's injuries were immediately apparent |

### 5. ConsistencyCheckerAgent

**File:** `backend/agents/consistency_checker.py`

**Input:** `list[FactClaim]` + source documents (dict)

**Output:** `list[ConsistencyFinding]`

**Approach:** Each claim ID maps to a dedicated checker method that inspects actual source document content. The checkers look for specific evidence strings in the police report, medical records, and witness statement, rather than returning fixed responses.

**This is the strongest part of the pipeline.** Cross-document comparison is grounded in actual document text, produces evidence snippets, and names the source documents. The date discrepancy and PPE discrepancy are both caught at high confidence (0.95 and 0.94) because multiple independent source documents directly contradict the MSJ.

**Mutation-aware:** Because the checkers inspect document content, the eval harness can mutate source documents and verify that findings change accordingly.

### 6. JudicialMemoAgent

**File:** `backend/agents/judicial_memo.py`

**Input:** `list[VerificationFlag]` (filtered to confidence >= 0.7)

**Output:** `str` (one paragraph)

**Approach:** Synthesizes high-confidence findings into a single neutral paragraph written for a judge. Only includes findings with confidence >= 0.7. Does not overstate low-confidence citation issues. Uses template-based assembly rather than free-form generation to avoid introducing hallucinations.

---

## Orchestrator

**File:** `backend/agents/orchestrator.py`

The orchestrator runs agents sequentially and builds the final report:

```mermaid
flowchart LR
    A["1. CitationExtractor"] --> B["2. AuthorityVerifier"]
    A --> C["3. QuoteChecker"]
    D["4. FactExtractor"] --> E["5. ConsistencyChecker"]
    B --> F["6. Flag Builder"]
    C --> F
    E --> F
    F --> G["7. JudicialMemo"]
    G --> H["VerificationReport"]

    style A fill:#dbeafe,stroke:#1e40af
    style B fill:#dbeafe,stroke:#1e40af
    style C fill:#dbeafe,stroke:#1e40af
    style D fill:#dbeafe,stroke:#1e40af
    style E fill:#dbeafe,stroke:#1e40af
    style F fill:#f3e8ff,stroke:#6b21a8
    style G fill:#fef3c7,stroke:#92400e
    style H fill:#dcfce7,stroke:#166534
```

**Failure handling:** Each agent call is wrapped in `_safe_run`, which catches all exceptions. If an agent fails, its output is `None`, an `AgentError` is recorded, and later agents continue. The `/analyze` endpoint always returns a structured report; it never returns a 500 due to a single agent crash. Missing agent outputs produce empty lists for their sections.

**Flag deduplication:** The flag builder maintains a `flag_ids_seen` set so that the same issue (e.g., the Privette overbreadth) is not flagged once as a citation issue and again as a quote issue.

**Flag ID mapping:** Fact-claim IDs are mapped to human-readable flag IDs:

| Claim ID | Flag ID |
|---|---|
| `incident_date` | `date_discrepancy` |
| `no_ppe` | `ppe_discrepancy` |
| `osha_compliance` | `osha_compliance_unverified` |
| `apex_control` | `harmon_control_disputed` |
| `limitations_elapsed` | `limitations_argument_weak` |

---

## Confidence Scoring

Confidence is emitted by each agent, not by a separate scoring agent. The rationale: the agent closest to the evidence is best positioned to score certainty.

**Scoring rules:**

| Condition | Confidence | Label |
|---|---|---|
| Direct contradiction across multiple source documents | 0.85-0.95 | high |
| Single-source contradiction or complication | 0.70-0.86 | high |
| LLM-only legal assessment on well-known authority | 0.67-0.90 | medium-high |
| Obscure authority without source text | 0.30-0.45 | low |
| No available evidence | 0.20-0.40 | low |

Labels are assigned by threshold: `high` >= 0.75, `medium` >= 0.5, `low` < 0.5.

---

## API

**Endpoint:** `POST /analyze`

**File:** `backend/main.py`

Returns:
```json
{
  "report": {
    "case_name": "...",
    "judicial_memo": "...",
    "citations": [...],
    "citation_verifications": [...],
    "quote_checks": [...],
    "fact_claims": [...],
    "consistency_findings": [...],
    "flags": [...],
    "agent_errors": [...],
    "metadata": {
      "document_count": 4,
      "agents_run": ["CitationExtractorAgent", ...],
      "fallback_used": true
    }
  }
}
```

The endpoint uses `def` (not `async def`) because the current pipeline is synchronous. This follows the FastAPI guidance that blocking code should use plain `def` to run in a threadpool.

---

## Eval Architecture

**File:** `backend/run_evals.py`

**Command:** `cd backend && python run_evals.py`

The eval harness measures pipeline quality across seven dimensions. It is designed to report honest scores, including ones below 100%, rather than optimizing for perfect metrics on a single case file.

```mermaid
flowchart TD
    DOCS["Source Documents"] --> PIPELINE["run_analysis()"]
    PIPELINE --> REPORT["VerificationReport"]

    REPORT --> GOLD["Core Gold Findings"]
    REPORT --> ASPIR["Aspirational Findings"]
    REPORT --> NEG["Negative Assertions"]
    REPORT --> GND["Evidence Grounding"]
    REPORT --> UNC["Uncertainty Accuracy"]
    DOCS --> MUT["Mutation Scenarios"]
    MUT --> PIPELINE2["run_analysis() (mutated)"]
    PIPELINE2 --> MUTRES["Mutation Results"]
    REPORT --> LIM["Known Limitations"]

    GOLD --> METRICS["Metrics Output"]
    ASPIR --> METRICS
    NEG --> METRICS
    GND --> METRICS
    UNC --> METRICS
    MUTRES --> METRICS
    LIM --> METRICS

    style GOLD fill:#dcfce7,stroke:#166534
    style ASPIR fill:#fef9c3,stroke:#854d0e
    style NEG fill:#fee2e2,stroke:#991b1b
    style GND fill:#dbeafe,stroke:#1e40af
    style UNC fill:#dbeafe,stroke:#1e40af
    style MUTRES fill:#f3e8ff,stroke:#6b21a8
    style LIM fill:#f5f5f5,stroke:#525252
    style METRICS fill:#fef3c7,stroke:#92400e
```

### Eval dimensions

#### 1. Core gold findings (precision + core_recall)

A set of six expected findings with semantic matching:

Each `ExpectedFinding` requires:
- Flag ID match
- Status within accepted set (e.g., `contradicted`)
- Required terms present in finding text (e.g., "March 14" and "March 12")
- Confidence within min/max bounds

**Precision** = matched core flags / total flags produced

**Core recall** = matched core flags / 6 expected

#### 2. Aspirational findings (expanded_recall)

One additional expected finding that the current pipeline does **not** catch: the Seabright/OSHA insulation overstatement. This is a real issue in the MSJ that the flag layer does not yet promote.

**Expanded recall** = (matched core + matched aspirational) / (core + aspirational count)

Current result: 6/7 = 0.857. This is intentional. The eval is more informative because it measures something the pipeline misses.

#### 3. Negative assertions

Three true statements from the case file that should **not** be flagged as problems:
- "Rivera was employed by Apex"
- "2200 West Olympic Boulevard"
- "left leg, lower back, and left wrist"

If the pipeline flags any of these as contradictions, that is a false positive.

#### 4. Evidence grounding

For every `ConsistencyFinding` with a `source_evidence` snippet, the eval checks whether that snippet actually appears in the named source document. This is the most direct hallucination test: it verifies that the pipeline is not fabricating evidence.

**Grounding rate** = grounded records / total records with evidence

#### 5. Uncertainty accuracy

For obscure citations (Whitmore, Kellerman, Torres), the eval checks that the pipeline returns `could_not_verify` with confidence <= 0.5. This rewards appropriate uncertainty rather than confident fabrication.

**Uncertainty accuracy** = correct uncertain calls / total obscure citations

#### 6. Mutation scenarios

Three document mutations that should cause specific flags to disappear:

| Mutation | Expected absent flag |
|---|---|
| Change MSJ date to March 12 | `date_discrepancy` |
| Change MSJ PPE text to say Rivera was wearing PPE | `ppe_discrepancy` |
| Remove Harmon direction evidence from police/witness docs | `harmon_control_disputed` |

**Mutation pass rate** = passed scenarios / total scenarios

This tests whether the pipeline is actually reading evidence or just returning hardcoded responses. Because the ConsistencyChecker inspects document content, these mutations correctly change the output.

#### 7. Known limitations

Metrics that honestly expose pipeline weaknesses:

| Metric | What it measures | Expected value |
|---|---|---|
| `citation_extraction_recall` | Fraction of expected citations extracted by regex | 1.0 (pattern list covers all citations in this case) |
| `authority_source_grounding_rate` | Fraction of authority checks grounded in retrieved source text | ~0.17 (only the statute check is grounded; all case-law checks are LLM-only) |
| `quote_exact_verification_rate` | Fraction of quote checks verified against primary source text | 0.0 (no source text is retrieved) |

These metrics are not failures. They are honest measurements of what the pipeline cannot yet do.

### Latest eval results

```json
{
  "precision": 1.0,
  "core_recall": 1.0,
  "expanded_recall": 0.857,
  "hallucination_rate": 0.0,
  "evidence_grounding_rate": 1.0,
  "uncertainty_accuracy": 1.0,
  "mutation_pass_rate": 1.0,
  "citation_extraction_recall": 1.0,
  "authority_source_grounding_rate": 0.167,
  "quote_exact_verification_rate": 0.0
}
```

### How to read these numbers

- **1.0 on core_recall** means the pipeline catches every issue it was designed to catch on this case file. It does not mean it catches every issue that exists.
- **0.857 expanded recall** means there is at least one real issue (Seabright/OSHA insulation overstatement) that the current flag layer does not surface.
- **0.167 authority source grounding** means only 1 of 6 citation verifications is grounded in anything beyond LLM parametric knowledge. This is the pipeline's biggest gap.
- **0.0 quote exact verification** means no direct quote was verified against its primary source. The pipeline can flag overbreadth but cannot confirm exact wording.
- **0.0 hallucination rate** on this case file is encouraging but is not proof that the pipeline never hallucinates. A more rigorous test would use adversarial inputs.

### Exit code

The eval exits non-zero only if core gold findings are missed, weak-matched, or if negative assertions produce false positives. Aspirational misses and known-limitation metrics do not cause exit 1, because they represent honest gaps rather than regressions.

---

## What would improve

1. **Legal database retrieval:** The authority verifier and quote checker would be dramatically stronger with access to case-law text. Even scraping free legal sites would move authority_source_grounding_rate from 0.17 to something meaningful.

2. **General citation parsing:** The current regex patterns are specific to this case file. A production system would use a general legal citation parser.

3. **LLM-based extraction with structured output:** Citation extraction and fact extraction could use LLM calls with JSON output for more flexible handling of different brief styles.

4. **Adversarial eval inputs:** The eval currently tests one case file. Adding adversarial documents (clean briefs, briefs with fabricated cases, briefs with subtle misquotes) would make metrics more meaningful.

5. **Per-category metric reporting:** Separate recall for citation issues, quote issues, and fact-consistency issues would make it clearer where the pipeline is strong and where it is weak.

6. **Confidence calibration:** The confidence scores are hand-tuned. A production system would benefit from calibration against a labeled dataset.
