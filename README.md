# BS Detector

Legal briefs lie. Not always intentionally — but they do. They cite cases that don't say what they claim. They quote authority with words quietly removed. They state facts that contradict the documents sitting right next to them.

Your task: build an AI pipeline that catches it.

## Setup

### Docker (recommended)

```bash
cp .env.example .env      # Add your OpenAI API key
docker compose up --build
```

The API runs at `http://localhost:8002`. The UI runs at `http://localhost:5175`.

Both services hot-reload — edit files on your host and changes appear automatically.

### Manual Setup

#### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # Add your OpenAI API key
uvicorn main:app --reload
```

The API runs at `http://localhost:8002`.

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

The UI runs at `http://localhost:5175`.

## The Task

Inside `backend/documents/` you'll find a small case file: a Motion for Summary Judgment in a personal injury lawsuit (*Rivera v. Harmon Construction Group*), along with a police report, medical records, and a witness statement.

Build a multi-agent pipeline that analyzes these documents and produces a structured verification report. Your pipeline should:

**Core (Tier 1)**
- Extract all citations from the Motion for Summary Judgment
- For each citation, assess whether the cited authority actually supports the proposition as stated
- Flag direct quotes for accuracy
- Produce structured output (JSON) — not a wall of prose

**Expected (Tier 2)**
- Build an eval harness that measures your pipeline's output quality. It must be runnable via a single command (e.g., `python run_evals.py`). At minimum, measure precision (avoiding false flags), recall (catching known flaws), and hallucination rate (not fabricating findings). You choose the approach — there's no prescribed framework or tooling.
- Cross-document consistency check: compare facts stated in the MSJ against the police report, medical records, and witness statement
- Express uncertainty appropriately — "could not verify" rather than fabricating a finding
- Pass structured data between agents, not raw text blobs

**Stretch (Tier 3)**
- At least 4 well-defined agents with distinct, non-overlapping roles
- A confidence scoring layer: each flag rated by how certain the pipeline is, with reasoning
- A judicial memo agent: synthesizes the top findings into a one-paragraph summary written for a judge
- Agent orchestration that handles failures gracefully
- A UI that displays the report in a structured, readable way — not just raw JSON
- A reflection document explaining the tradeoffs you made and what you'd do differently

## Deliverables

1. A working `POST /analyze` endpoint that returns a structured verification report
2. Agent code with clear, named agents and explicit prompts
3. A runnable eval suite with instructions in your README on how to run it
4. A brief reflection (in the repo or as a separate file) on your design decisions and tradeoffs

## Time

6 hours. This is intentionally scoped beyond what most candidates will finish. Where you invest your time matters more than finishing everything. A well-tested pipeline that catches 3 flaws is stronger than an untested one that attempts 10.

## Evals

We run your eval suite as part of our review. Document how to run it in your README. We care more about thoughtful metric design than perfect scores — an eval that honestly reports 60% recall tells us more than one that reports 100% on cherry-picked cases.

### Run the Verification Pipeline

Start the backend, then call the analysis endpoint:

```bash
cd backend
uvicorn main:app --reload --port 8002
```

```bash
curl -X POST http://localhost:8002/analyze
```

The endpoint returns a structured JSON report with extracted citations, citation verification, quote checks, fact claims, cross-document findings, normalized flags, agent errors, metadata, and a one-paragraph judicial memo.

### Run Evals

From the backend directory:

```bash
cd backend
python run_evals.py
```

The eval harness runs the pipeline on the included Rivera case file and compares the report against a small gold set of known flaws:

- incident-date discrepancy
- PPE discrepancy
- unverified OSHA compliance claim
- disputed Harmon/Apex control framing
- overbroad Privette quote
- weak limitations argument

The eval uses semantic concept matching instead of exact `flag.id` matching. Each expected finding defines required concepts, accepted statuses, and confidence bounds, so LLM-generated IDs like `incident_date_march_14_2021` can still match the gold `date_discrepancy` finding when the substance is correct.

Metrics reported:

- `precision`: semantically matched core, weak, and aspirational flags divided by all produced flags
- `core_recall`: matched core gold flags divided by expected core gold flags
- `expanded_recall`: core plus aspirational findings, including real issues the current pipeline does not yet promote to flags
- `weak_match_count`: semantically relevant core findings with imperfect status or confidence
- `hallucination_rate`: unsupported non-uncertainty flags divided by all produced flags
- `evidence_grounding_rate`: consistency findings whose evidence snippets appear in named non-MSJ source documents
- `uncertainty_accuracy`: obscure citations correctly marked with uncertainty and low confidence
- `mutation_pass_rate`: document mutations that remove the expected flag
- `clean_case_false_positive_rate`: contradiction/fabrication flags emitted on a clean synthetic brief
- `fabricated_citation_detection_rate`: detection of an obvious synthetic fabricated citation
- `authority_source_grounding_rate`: citation checks grounded in retrieved source authority text; currently expected to be low because this implementation is LLM-only for legal authority
- `quote_exact_verification_rate`: direct quote checks verified against source authority text; currently expected to be low without case-law retrieval

This implementation requires `OPENAI_API_KEY`. The analysis agents call the LLM for extraction, authority verification, quote checking, fact consistency analysis, and judicial memo synthesis. If the key is missing or an LLM response fails schema validation, the affected agent records an error instead of using deterministic fallback logic.

### Interpreting LLM Eval Results

The LLM-only eval is designed to measure substance rather than deterministic labels. A finding can pass if its text contains the required concepts, uses an accepted status, and falls within the confidence range. Findings with the right substance but imperfect status or confidence are reported as `weak_matches`, not hallucinations.

The eval still intentionally exposes model weaknesses:

- Citation extraction recall shows whether the model found expected citations, including short-form citations like `Id. at 702`.
- Uncertainty accuracy shows whether the model refuses to over-trust obscure authorities without source text.
- Grounding checks require fact evidence to appear in non-MSJ source documents, not merely in the motion itself.
- Authority and quote source-grounding rates remain low unless primary authority text is actually supplied or retrieved.
- Mutation tests now look for semantic issues after document changes, not fixed flag IDs.

## AI Usage

Use everything. That's the job. We want to see how you use it, not whether you do.

## Evaluation

We are evaluating:

1. How you decompose the problem into agents
2. How precisely you write prompts
3. The quality of your eval approach — do you measure what matters?
4. How far you get through the spec
5. How honest your reflection is

Not lines of code.
