# Post-00 audit — first failing stage

Attributes every wrong answer of the `post-01` baseline, on the eval v1 **dev** split, to the first pipeline stage that lost the evidence. This produces the lead chart of post 00.

> No results are committed yet. `failure_attribution.json` appears here once the audit has run on real `post-01` traces. Never commit synthetic or hand-edited numbers to this file.

## Cascade

```
system → parse → chunk → index → retrieve → assemble → [human] generate | cite
```

| Stage | Check (fails → attributed here) | Needs |
|---|---|---|
| system | request errored (timeout, 5xx) | `trace.error` |
| parse | gold span text not found in the parsed document (normalized exact match, then fuzzy ≥ `--min-similarity`) | parsed text |
| chunk | no chunk covers ≥ θ of the located gold span | chunk offsets |
| index | covering chunks not indexed, or embedded with a different model than the query | `embedding_model`, `indexed` |
| retrieve | no usable covering chunk in the retrieved top-k | `retrieved_ids` |
| assemble | covering chunk retrieved but absent or truncated in the prompt | `prompt_chunk_ids` |
| generate / cite | evidence reached the prompt → **human label** | `human_labels.csv` |

- Multiple gold spans: `evidence_mode: "all"` (multi-hop; earliest failure wins) or `"any"` (one span suffices; the span that got furthest decides).
- Unanswerable questions that got an answer → `generate`, sub-label `FP1`.
- Items tagged `acl_probe` or `injection` are excluded from the distribution and listed under `security_items`.
- θ defaults to 0.5; `--sensitivity` re-runs at 0.4 / 0.5 / 0.6 so the chunk-vs-retrieve split can be reported with its sensitivity.

## Inputs

**`parsed_docs.jsonl`** — one line per document version, written by the `post-01` worker:

```json
{"doc_id": "d1", "doc_version": "v1", "text": "<parsed text>",
 "chunks": [{"chunk_id": "c1", "char_start": 120, "char_end": 1840,
             "embedding_model": "<model id>", "indexed": true}]}
```

**`traces.jsonl`** — one line per dev question, from the `post-01` structured request logs plus the correctness label:

```json
{"question_id": "q017", "workload_class": "multimodal", "tags": ["table"],
 "correct": false, "error": null, "refused": false, "evidence_mode": "all",
 "gold_spans": [{"doc_id": "d1", "doc_version": "v1", "text": "<gold evidence text>"}],
 "query_embedding_model": "<model id>",
 "retrieved_ids": ["c9", "c1", "c4"], "prompt_chunk_ids": ["c9", "c1", "c4"]}
```

`correct` is the binary answer-correctness label (human at this stage).

**`human_labels.csv`** — only for items reported as `needs_human`:

```csv
question_id,stage,sub_label
q017,generate,FP4
q031,cite,
```

`stage` ∈ {`generate`, `cite`}; `sub_label` optional, Barnett FP4–FP7, `generate` only.

## Run

```bash
make audit            # uses traces.jsonl, parsed_docs.jsonl, human_labels.csv in this directory
# or
python eval/audits/post-00/failure_attribution.py \
  --traces traces.jsonl --docs parsed_docs.jsonl --labels human_labels.csv \
  --theta 0.5 --sensitivity 0.4 0.5 0.6
```

Typical loop: run once without labels → label the `needs_human` items → run again. The script prints a per-class Markdown table and writes `failure_attribution.json`.

## Limits (state these in the article)

- First failing stage hides compound failures: a bad chunk plus a bad generation counts once, as `chunk`.
- Small n per class; report counts, not percentages.
- One annotator for generate/cite labels, one pinned model set, naive configuration by design.
- θ moves items between `chunk` and `retrieve`; report the sensitivity row.
