# Production RAG Architecture — Stage-by-Stage Contracts, Failures, Fixes

Companion repository for the Medium series **RAG in Production — From Baseline to Operated System** (Towards AI, 25 posts).

The series builds one RAG system in the open, from a naive baseline to an operated production service. Each post adds or swaps one component behind a typed stage contract and measures the change against one frozen eval set.

> **Status:** scaffold only. Tag `post-00` currently contains the architecture docs and the failure-attribution audit tooling. The baseline service (`post-01`) and eval v1 (`post-02`) are not built yet, so no results are published here.

---

## How this repo works

| Rule | Why |
|---|---|
| **One repo, one tag per post** (`post-00` … `post-24`) | `git checkout post-NN` reproduces any article. |
| **Config as code** — every post is `configs/post-NN.yaml` + at most one new component | Changes are diffs you can read, not rewrites. |
| **Eval v1 frozen at `post-02`** — dev 30% (tuning allowed) / test 70% (reported) | Stops 20 posts of silent overfitting. |
| **Span-level gold evidence** `{doc_id, doc_version, page, char_start, char_end}` | Ground truth survives chunking changes. |
| **Per-workload-class reporting with 95% bootstrap CIs**; a delta inside the CI = "no measurable change" | Aggregate scores hide which documents a change helped. |
| **Results keyed by config hash** in `eval/results/post-NN/` | Every number in every article traces to a run. |
| **Signals vs policy** — retrieval and generation emit signals; a deterministic policy layer owns ACL, refusal, citation validation | Refusal, access control and citation behaviour stay testable and auditable. |
| **A tag exists only if `make test && make smoke` pass** | Tags are runnable, not snapshots. |

Architecture, stage contracts and the failure taxonomy: [`docs/architecture.md`](docs/architecture.md).
Series plan and status: [`docs/series-manifest.md`](docs/series-manifest.md).

---

## Series index

Status: `planned → researched → ready → drafted → published`. Links are added as posts publish.

| # | Track | Title | Repo tag | Status |
|---|---|---|---|---|
| 00 | Pillar | Where RAG Actually Breaks | `post-00` | ready (awaiting audit) |
| 01 | Foundations | A RAG Baseline Worth Measuring: FastAPI, pgvector, Azure Queues | `post-01` | ready |
| 02 | Foundations | Measure Before You Optimize: A RAG Eval Harness With Span-Level Ground Truth | `post-02` | planned |
| 03 | Foundations | Ingestion That Survives Real PDFs | `post-03` | planned |
| 04 | Foundations | Chunking Is a Retrieval Decision | `post-04` | planned |
| 05 | Foundations | Choosing Embeddings and Sizing a pgvector Index | `post-05` | planned |
| 06 | Foundations | Dense, Sparse, Hybrid: Retrieval You Can Explain | `post-06` | planned |
| 07 | Foundations | Grounded Generation: Citations, Context Assembly, Refusal | `post-07` | planned |
| 08 | Accuracy | Reranking: Buying Precision With Latency | `post-08` | planned |
| 09 | Accuracy | Query Transformation, Measured | `post-09` | planned |
| 10 | Accuracy | Metadata Filtering and Structured Retrieval | `post-10` | planned |
| 11 | Accuracy | Hierarchical and Graph Indexes | `post-11` | planned |
| 12 | Accuracy | Agentic Retrieval: When the Loop Is Worth the Latency | `post-12` | planned |
| 13 | Workloads | Small Documents: When Not to Retrieve | `post-13` | planned |
| 14 | Workloads | Medium Documents: Section-Aware and Parent-Child Retrieval | `post-14` | planned |
| 15 | Workloads | Large Documents: Summaries, Section Routing, Map-Reduce | `post-15` | planned |
| 16 | Workloads | Multimodal Documents: Tables, Figures, Scans | `post-16` | planned |
| 17 | Workloads | Multi-Domain Corpora: Routing and Per-Domain Indexes | `post-17` | planned |
| 18 | Performance | Latency and Cost Budgets for RAG | `post-18` | planned |
| 19 | Production | Securing RAG: Access Control, Injection, PII, Tenancy | `post-19` | planned |
| 20 | Production | Failure-Tolerant RAG: Timeouts, Fallbacks, Idempotent Ingestion | `post-20` | planned |
| 21 | Production | Deploying RAG on Azure: Async Ingestion and Zero-Downtime Reindex | `post-21` | planned |
| 22 | Production | Observing RAG: Tracing, Drift, Feedback Loops | `post-22` | planned |
| 23 | Production | Continuous Evaluation: Regression Gates and Test-Set Maintenance | `post-23` | planned |
| 24 | Capstone | Reference Architecture and Decision Matrix by Workload | `post-24` | planned |

### Reading paths

| Path | For | Posts |
|---|---|---|
| **Linear** | Python + LLM API experience, new to retrieval | 00 → 24 in order |
| **Production fast path** | Knows RAG basics, needs production depth | 00 → 02 → 06 → 07 → 08 → *your workload (13–17)* → 18 → 19 → 20 → 21 → 22 → 23 → 24 |
| **Regulated / security** | Access control, auditability, compliance | 00 → 01 → 02 → 07 → 10 → 19 → 20 → 23 → 24 |
| **Workload** | One document type to solve now | 00 → 02 → 04 → *class post (13–17)* → 24 |

### Workload classes

Page bands are reader-facing labels only. Routing (from post 03) keys on a measured `DocProfile`: tokens, heading depth, table/figure density, scanned vs born-digital, language and domain.

| Class | Label | Dedicated post |
|---|---|---|
| Small | 1–50 pages | 13 |
| Medium | 50–100 pages | 14 |
| Large | 100+ pages | 15 |
| Multimodal | table-, figure- or scan-heavy | 16 |
| Multi-domain | several domains in one corpus | 17 |

---

## Repository layout

Present now:

```
docs/
  architecture.md                    # two-path diagram, stage contracts, failure taxonomy, security surface
  series-manifest.md                 # series plan and status (source of truth)
eval/audits/post-00/
  failure_attribution.py             # deterministic first-failing-stage cascade
  README.md                          # input schema and run instructions
tests/
  test_failure_attribution.py
Makefile  pyproject.toml
```

Planned (arrives with `post-01` and `post-02`):

```
apps/api/            # FastAPI: /query, /ingest, /health
apps/worker/         # queue consumer: parse → chunk → embed → upsert
rag/                 # contracts, ingest, chunk, embed, index, retrieve, generate, policy
configs/post-NN.yaml
eval/datasets/v1/    # corpus manifest, questions, gold spans, splits
eval/metrics/  eval/judges/  eval/results/post-NN/
migrations/  infra/  # docker-compose: Postgres + pgvector, Azurite
```

---

## Quick start (current tag)

```bash
python -m pip install -e ".[dev]"
make test
```

The failure-attribution audit needs traces from the `post-01` baseline on the eval v1 dev split; see [`eval/audits/post-00/README.md`](eval/audits/post-00/README.md).

---

## License

Code: Apache-2.0 (LICENSE file to be added). Corpus documents keep their own licenses, recorded per document in the eval v1 corpus manifest.
