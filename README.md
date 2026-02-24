# BS Detector

Legal briefs lie. Not always intentionally — but they do. They cite cases that don't say what they claim. They quote authority with words quietly removed. They state facts that contradict the documents sitting right next to them.

Your task: build an AI pipeline that catches it.

## Setup

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # Add your OpenAI API key
uvicorn main:app --reload
```

The API runs at `http://localhost:8000`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The UI runs at `http://localhost:5173`.

## The Task

Inside `backend/documents/` you'll find a small case file: a Motion for Summary Judgment in a personal injury lawsuit (*Rivera v. Harmon Construction Group*), along with a police report, medical records, and a witness statement.

Build a multi-agent pipeline that analyzes these documents and produces a structured verification report. Your pipeline should:

**Core (Tier 1)**
- Extract all citations from the Motion for Summary Judgment
- For each citation, assess whether the cited authority actually supports the proposition as stated
- Flag direct quotes for accuracy
- Produce a structured output (JSON or markdown) — not a wall of prose

**Expected (Tier 2)**
- Cross-document consistency check: compare facts stated in the MSJ against the police report, medical records, and witness statement
- Flag missing legal elements: does the MSJ address all required elements of the legal tests it invokes?
- Express uncertainty appropriately — "could not verify" rather than fabricating a finding
- Pass structured data between agents, not raw text blobs
- At least 4 well-defined agents with distinct, non-overlapping roles

**Stretch (Tier 3)**
- A confidence scoring layer: each flag rated by how certain the pipeline is, with reasoning
- A judicial memo agent: synthesizes the top findings into a one-paragraph summary written for a judge
- Agent orchestration that handles failures gracefully
- A UI that displays the report in a structured, readable way — not just raw JSON
- A reflection document explaining the tradeoffs you made and what you'd do differently

## Deliverables

1. A working `POST /analyze` endpoint that returns a structured verification report
2. Agent code with clear, named agents and explicit prompts
3. A brief reflection (in the repo or as a separate file) on your design decisions and tradeoffs

## Time

4 hours. This is intentionally scoped beyond what most candidates will finish. Where you choose to invest your time tells us more than a checklist.

## AI Usage

Use everything. That's the job. We want to see how you use it, not whether you do.

## Evaluation

We are evaluating: how you decompose the problem into agents, how precisely you write prompts, how far you get through the spec, and how honest your reflection is. Not lines of code.
