# BS Detector — Production Readiness Plan

This is the plan for taking the prototype to a paid MVP for law firms. It is
opinionated on purpose. I call out what I would build first, what I would defer, and
where I expect the system to break.

---

## 1. Assumptions (and which ones would change the design)

| # | Assumption | If it changed |
|---|-----------|---------------|
| A1 | Launch scale: low hundreds of concurrent users, dozens–hundreds of docs per matter, analyses take **minutes** (many model calls). | If analyses were sub-second, I'd drop the async job system entirely — it's the single biggest piece of complexity and only justified by minute-scale, multi-call workflows. |
| A2 | Output is **decision-support, not autonomous**. A lawyer reviews every report; we are never the final word. | If outputs were auto-filed, I'd need far heavier guardrails, sign-off, and malpractice-grade audit. |
| A3 | Data is **confidential and often privileged**. Some firms will demand we never train on their data and can prove deletion. | Drives zero-retention LLM usage, per-tenant encryption, and audit from day one — not deferred. |
| A4 | Quality is the product. A confident wrong flag is worse than a missed one — it erodes the trust that makes a lawyer keep using it. | Biases every tradeoff toward precision and abstention over recall. |
| A5 | We stay on a hosted frontier LLM (OpenAI/Anthropic) for the MVP; no self-hosted models yet. | Self-hosting only if a customer contractually forbids third-party processors. |

The honest headline: **this is a long-running, quality-sensitive, multi-tenant
workflow product over confidential data.** Almost every choice below follows from
those four words.

---

## 2. System components and why these boundaries

```
                         ┌──────────────┐
   Browser ── HTTPS ───► │  API service │ ──► Postgres (matters, jobs, flags, audit)
                         │  (stateless) │ ──► Object store (encrypted documents)
                         └──────┬───────┘
                                │ enqueue job
                                ▼
                         ┌──────────────┐
                         │ Job queue    │  (durable, at-least-once)
                         └──────┬───────┘
                                ▼
                         ┌──────────────┐
                         │ Pipeline     │ ──► LLM provider (zero-retention)
                         │ workers      │ ──► Vector store (per-tenant retrieval)
                         │ (LangGraph)  │ ──► writes flags + traces back to Postgres
                         └──────────────┘
```

- **API service is stateless.** It authenticates, authorizes, accepts uploads,
  enqueues jobs, and serves status/results. It does *no* model work, so it scales and
  deploys independently of the slow, expensive part.
- **The pipeline runs in workers behind a durable queue, not in the request.** This is
  the core architectural decision. A 2–5 minute, multi-model-call analysis cannot live
  in an HTTP request: it would tie up connections, die on deploys, and give the user no
  visibility. Decoupling buys retries, backpressure, horizontal scale, and progress
  streaming.
- **Postgres is the system of record** for matters, jobs, flags, and the audit log —
  small, relational, transactional data.
- **Object storage holds documents**, encrypted per tenant. Documents are large, binary,
  and rarely queried relationally.
- **Vector store is per-tenant** for retrieval over large matters (see §3). It is a
  derived index, not a source of truth.

I'd start as a **modular monolith**: one API codebase and one worker codebase sharing
models, not a fleet of microservices. The agents are already cleanly separated *in
code*; I don't need them separated *in infrastructure* until one of them becomes an
independent scaling or failure domain. Splitting early would buy distributed-systems
pain before there's a reason for it.

---

## 3. How an analysis moves through the system

1. **Upload.** Client uploads documents to the API, which streams them to encrypted
   object storage and records metadata in Postgres. Documents are content-hashed for
   dedupe and idempotency.
2. **Request analysis.** API creates a `job` row (`status=queued`) and enqueues a
   message with the matter id + document set. Returns a `job_id` immediately.
3. **Ingest & index.** A worker extracts text (OCR for scanned PDFs — real litigation
   documents are scans), chunks it, and builds a **per-tenant** vector index. For a
   100-document matter we cannot stuff everything into context; cross-doc checking
   becomes *retrieve the passages relevant to each MSJ claim*, not "send all docs."
4. **Run the graph.** The LangGraph pipeline runs the five agents. Each node writes its
   partial result and a trace to Postgres as it completes, so progress is durable and
   streamable. Per-node failures are caught and recorded (already implemented).
5. **Stream status.** Client polls or subscribes (SSE/WebSocket) to job status; flags
   appear incrementally as agents finish.
6. **Final report.** When the graph completes, the job is marked `done` and the full
   structured report (flags, confidence, memo, citations, errors) is available.

**Durable vs. recomputable:**

| Durable (store it) | Recomputable (cache / rebuild) |
|--------------------|-------------------------------|
| Uploaded documents (source of truth) | Extracted/OCR'd text |
| Job records + status + timestamps | Vector embeddings / index |
| Final flags, confidence, memo | Intermediate agent outputs (kept for audit, not correctness) |
| Audit log (who saw/ran what) | Anything we can re-derive by re-running the pipeline |
| LLM request/response traces (for debugging + eval) | |

Rule of thumb: **store the inputs and the verified outputs; treat everything the
pipeline computes in between as a cache.** That keeps the durable surface small and
makes re-running cheap.

---

## 4. Where it fails first, and recovery

Ranked by what I actually expect to break:

1. **LLM provider — rate limits, timeouts, latency spikes, outages.** This is the
   number-one operational risk and the most likely page. Mitigation: per-node retries
   with backoff, a circuit breaker, a secondary provider/model for failover, and
   partial-result delivery (the graph already degrades gracefully — a failed node
   records an error and the rest of the report still ships). Jobs are resumable from the
   last completed node via checkpointing.
2. **Malformed model output.** Structured outputs reduce but don't eliminate this.
   Schema-validate every agent result; on failure, one repair retry, then mark that
   node failed rather than poisoning downstream agents.
3. **Cost runaway.** A few large matters fanned out across agents can 10× spend
   silently. Mitigation in §7.
4. **Poison documents.** A 900-page scanned PDF, a corrupt file, or a prompt-injection
   payload embedded in a document ("ignore previous instructions"). Mitigation: size/
   page caps, content sanitization, and treating document text as *data, never
   instructions* in prompts.
5. **Queue backlog under spikes.** Recovery: autoscale workers on queue depth; shed or
   defer low-priority jobs; always keep the API responsive even when workers are behind.

What I explicitly do **not** solve at MVP: multi-region failover, exactly-once
semantics (at-least-once + idempotent jobs is enough), and self-healing data repair.

---

## 5. Tenant isolation & protecting confidential documents

This is table stakes for selling to law firms, so it ships in the **first** increment,
not later.

- **Isolation:** every row carries a `tenant_id`; all queries are scoped through a data
  layer that refuses an unscoped query. Object storage is partitioned by tenant with
  per-tenant encryption keys (envelope encryption). For firms that demand it, this is
  the seam to upgrade to per-tenant databases/buckets without changing app logic.
- **Encryption:** TLS in transit; at rest everywhere, with per-tenant keys so a key
  revocation provably renders one tenant's data unreadable (supports "prove deletion").
- **LLM data handling:** zero-retention API tier, no training on customer data,
  contractually and in config. This is a sales blocker if we get it wrong.
- **Access control:** org → matter → document RBAC. A user sees only their org's
  matters. Privileged-document handling is a first-class concept, not a tag.
- **Audit log:** append-only record of who uploaded, ran, viewed, and exported what.
  Lawyers will ask for this; build it from day one because it's painful to backfill.
- **PII/privilege:** minimize what leaves our boundary; redact where feasible before
  sending to the model.

---

## 6. Knowing whether it's correct, healthy, and improving

Three different questions, three different instruments:

- **Correct (quality):** the eval harness from Part 1 becomes CI infrastructure. Every
  prompt or model change runs against a growing labeled set (the *gold matters*) and
  must not regress precision/recall/hallucination beyond a threshold. We add clean,
  flaw-free briefs to measure false-positive rate on sound filings. **Human-in-the-loop
  is a product feature, not just QA:** lawyers accept/reject flags, and that feedback
  becomes new labeled eval data — the flywheel that improves the product.
- **Healthy (ops):** per-agent latency, error rate, queue depth, job success/duration,
  provider error rate. Distributed tracing per job so one slow analysis is debuggable
  end to end. Alert on queue backlog and provider error spikes — the two real pagers.
- **Improving:** track flag acceptance rate by lawyers over time, per flag type. A
  falling acceptance rate on a flag type is an early warning that a prompt or model
  drifted, before it shows up as churn.

I'd keep every LLM request/response trace (within retention limits) precisely so a
disputed flag can be reproduced and replayed against a new prompt.

---

## 7. Cost controls

- **Model tiering per agent.** Extraction and confidence scoring can run on a cheaper/
  smaller model; only the verification agents need the strongest one. This is the
  biggest single lever and the agents are already separated to allow it.
- **Retrieval over stuffing.** Per-tenant vector search means cross-doc checks send
  relevant passages, not whole matters — the dominant token cost at scale.
- **Caching by content hash.** Re-running an unchanged document/matter returns cached
  results; identical chunks reuse embeddings.
- **Per-tenant budgets + alerts**, and a hard ceiling per job so one pathological matter
  can't run away.

---

## 8. Sequencing — what I'd build first

**Increment 1 (make it real and safe):** async job system (queue + workers) so analyses
survive deploys and scale; Postgres system of record; encrypted per-tenant document
storage; auth + RBAC + audit log; status polling. This is the smallest thing that is
*both* a usable product *and* safe to put confidential data into. Tenant isolation and
audit are in here, not deferred — they're unsellable to add later.

**Increment 2 (make it good):** retrieval/indexing for large matters; the eval harness
wired into CI as a quality gate; the human-in-the-loop accept/reject feedback loop;
per-agent observability and tracing.

**Increment 3 (make it scale & defensible):** model tiering and cost controls; provider
failover; autoscaling on queue depth; durable checkpointing/resume.

**Deferred on purpose:** microservice decomposition, multi-region, self-hosted models,
fine-tuning. None of these earn their complexity until a real customer or scale number
forces them.

---

## 9. What stays flexible (because the product is early)

- **The agent graph itself.** Roles, prompts, and even the number of agents will change
  as we learn what lawyers trust. Keeping prompts centralized and state typed makes the
  graph cheap to re-shape — that flexibility is deliberate.
- **The model and provider.** Abstracted behind one call site so we can tier, swap, or
  fail over without touching agent logic.
- **The retrieval strategy.** Whether cross-doc checking is full-context, RAG, or hybrid
  depends on real matter sizes we haven't seen yet.

The parts I would *not* leave flexible — tenant isolation, encryption, audit — are the
ones that are expensive to retrofit and fatal to get wrong with legal data. Everything
about *how well it detects BS* should stay soft; everything about *how safely it holds
client data* should be hard from day one.
