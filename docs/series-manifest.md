# Series Manifest — RAG in Production (`rag-prod`)

Source of truth for series status. Updated after each post publishes: status, URL, repo tag and headline eval numbers.

**Series:** RAG in Production — From Baseline to Operated System
**Publication:** Towards AI · free · 1 post / 2 weeks · 25 posts (00–24)
**Repo:** https://github.com/Alwyn25/Production-RAG-Architecture--Stage-by-Stage-Contracts-Failures-Fixes
**Eval set:** v1, frozen at tag `post-02`
**Last updated:** 2026-09-29 · curriculum status: **awaiting author approval**

## Posts

| brief_id | Title | Kind | Status | URL | Repo tag | Eval baseline (test split) |
|---|---|---|---|---|---|---|
| rag-prod-00 | Where RAG Actually Breaks | stable | ready (outline; awaiting audit) | — | post-00 | diagnostic only |
| rag-prod-01 | A RAG Baseline Worth Measuring | stable | ready | — | post-01 | defines baseline |
| rag-prod-02 | Measure Before You Optimize | moving | planned | — | post-02 | [TODO] post-01 per class |
| rag-prod-03 | Ingestion That Survives Real PDFs | moving | planned | — | post-03 | post-02 |
| rag-prod-04 | Chunking Is a Retrieval Decision | stable | planned | — | post-04 | post-03 |
| rag-prod-05 | Choosing Embeddings and Sizing a pgvector Index | moving | planned | — | post-05 | post-04 |
| rag-prod-06 | Dense, Sparse, Hybrid | stable | planned | — | post-06 | post-05 |
| rag-prod-07 | Grounded Generation | stable | planned | — | post-07 | post-06 |
| rag-prod-08 | Reranking | moving | planned | — | post-08 | post-07 |
| rag-prod-09 | Query Transformation, Measured | moving | planned | — | post-09 | post-07 |
| rag-prod-10 | Metadata Filtering and Structured Retrieval | stable | planned | — | post-10 | post-07 |
| rag-prod-11 | Hierarchical and Graph Indexes | moving | planned | — | post-11 | post-07 |
| rag-prod-12 | Agentic Retrieval | moving | planned | — | post-12 | post-09 |
| rag-prod-13 | Small Documents | moving | planned | — | post-13 | best of 08–12 |
| rag-prod-14 | Medium Documents | stable | planned | — | post-14 | best of 08–12 |
| rag-prod-15 | Large Documents | moving | planned | — | post-15 | post-14 |
| rag-prod-16 | Multimodal Documents | moving | planned | — | post-16 | best of 08–12 |
| rag-prod-17 | Multi-Domain Corpora | moving | planned | — | post-17 | best of 08–12 |
| rag-prod-18 | Latency and Cost Budgets | moving | planned | — | post-18 | per-class configs 13–17 |
| rag-prod-19 | Securing RAG | moving | planned | — | post-19 | post-18 |
| rag-prod-20 | Failure-Tolerant RAG | stable | planned | — | post-20 | post-19 |
| rag-prod-21 | Deploying RAG on Azure | stable | planned | — | post-21 | post-20 |
| rag-prod-22 | Observing RAG | moving | planned | — | post-22 | post-21 |
| rag-prod-23 | Continuous Evaluation | stable | planned | — | post-23 | post-22 |
| rag-prod-24 | Reference Architecture and Decision Matrix | stable | planned | — | post-24 | post-01 (cumulative) |

Status values: planned → researched → ready → drafted → published.

## Build and publish order

`post-01` code → `post-02` code + eval v1 → post-00 audit → publish 00, 01, 02 on cadence. Post 00 is written third and published first.

The `post-00` tag is cut after the audit runs, so it carries `eval/audits/post-00/failure_attribution.json`. Until then the docs and audit tooling live on branch `post-00-docs`.

## Glossary

| Term | Definition |
|---|---|
| Stage | One of parse, chunk, index, retrieve, assemble, generate, cite (ingest = parse + chunk) |
| Stage contract | Typed input/output of a stage (Document, Chunk, RetrievedChunk, Answer) |
| DocProfile | Deterministic document features used for routing: tokens, heading depth, table/figure density, scanned vs born-digital, language, domain |
| Workload class | Reader-facing label (small, medium, large, multimodal, multi-domain) derived from DocProfile |
| Gold span | `{doc_id, doc_version, page, char_start, char_end}` evidence for a question |
| Hit | Retrieved chunk covering ≥ θ of a gold span |
| First failing stage | Earliest stage, in pipeline order, whose audit check fails for a wrong answer |
| Pre-filter | Access predicates applied inside the retrieval query, before ranking |
| Policy layer | Deterministic code owning ACL, refusal thresholds, citation validation |
| Citation validity | Share of citations whose chunk supports the cited claim |
| Refusal accuracy | Share of unanswerable questions correctly refused |
| ACL probe | Question whose evidence exists only in a document the test principal cannot access |
| Config hash | Hash of the pipeline config; keys every result file |
| Eval v1 | Frozen dataset at tag post-02; dev 30% / test 70% |

## Open TODOs

- [ ] Author approves curriculum
- [ ] Decide audit taxonomy (`index` as its own stage) and audit size (30 questions vs full dev split)
- [ ] Build `post-01` (baseline service)
- [ ] Assemble eval v1 corpus with verified licenses; build `post-02`
- [ ] Decide span-hit threshold θ (proposed 0.5); choose and pin judge model
- [ ] Pin embedding and generation model versions for `post-01`
- [ ] Run post-00 audit; cut tag `post-00`
- [ ] Add LICENSE (Apache-2.0)
- [x] Repo created and URL recorded
- [x] Towards AI submission requirements verified (2026-09-29)
