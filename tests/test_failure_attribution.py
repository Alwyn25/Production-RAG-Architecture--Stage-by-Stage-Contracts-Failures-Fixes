"""Unit tests for the post-00 attribution cascade. All fixtures are synthetic."""

import csv
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "failure_attribution", ROOT / "eval/audits/post-00/failure_attribution.py"
)
fa = importlib.util.module_from_spec(_spec)
sys.modules["failure_attribution"] = fa  # dataclasses resolve the module by name
_spec.loader.exec_module(fa)

TEXT = (
    "Section 1. Overview of the filing.\n"
    "Total revenue for fiscal 2025 was 4.2 billion dollars.\n"
    "Section 2. Risk factors include currency exposure."
)
SPAN = "Total revenue for fiscal 2025 was 4.2 billion dollars."
S = TEXT.index(SPAN)
E = S + len(SPAN)
MODEL = "embed-v1"


def doc(chunks):
    return {("d1", "v1"): fa.ParsedDoc("d1", "v1", TEXT, chunks)}


def good_chunks():
    return [
        fa.Chunk("c0", 0, S, MODEL),
        fa.Chunk("c1", S, E, MODEL),
        fa.Chunk("c2", E, len(TEXT), MODEL),
    ]


def trace(**kw):
    base = dict(
        question_id="q1",
        workload_class="large",
        correct=False,
        gold_spans=[fa.GoldSpan("d1", "v1", SPAN)],
        query_embedding_model=MODEL,
        retrieved_ids=["c1", "c2"],
        prompt_chunk_ids=["c1", "c2"],
    )
    base.update(kw)
    return fa.Trace(**base)


def stage(t, docs=None, theta=0.5):
    a = fa.attribute(t, docs or doc(good_chunks()), theta=theta)
    return a.stage if a else None


def test_correct_answer_is_not_attributed():
    assert stage(trace(correct=True)) is None


def test_system_error_wins():
    assert stage(trace(error="timeout after 30s")) == "system"


def test_parse_failure_when_span_missing():
    broken = {("d1", "v1"): fa.ParsedDoc("d1", "v1", "Section 1. Overview.", [fa.Chunk("c0", 0, 20, MODEL)])}
    assert stage(trace(), broken) == "parse"


def test_parse_tolerates_whitespace_and_case_noise():
    noisy = TEXT.replace("Total revenue", "TOTAL\n  revenue")
    s = noisy.index("TOTAL")
    e = s + len("TOTAL\n  revenue for fiscal 2025 was 4.2 billion dollars.")
    d = {("d1", "v1"): fa.ParsedDoc("d1", "v1", noisy, [fa.Chunk("c1", s, e, MODEL)])}
    assert stage(trace(retrieved_ids=["c1"], prompt_chunk_ids=["c1"]), d) == fa.NEEDS_HUMAN


def test_chunk_failure_when_span_is_split():
    mid = S + len(SPAN) // 2
    split = [fa.Chunk("a", 0, mid - 5, MODEL), fa.Chunk("b", mid - 5, len(TEXT), MODEL)]
    # each half covers < 0.9 of the span
    assert stage(trace(retrieved_ids=["a", "b"], prompt_chunk_ids=["a", "b"]), doc(split), theta=0.9) == "chunk"


def test_theta_moves_items_between_chunk_and_retrieve():
    mid = S + 20
    split = [fa.Chunk("a", 0, mid, MODEL), fa.Chunk("b", mid, len(TEXT), MODEL)]
    t = trace(retrieved_ids=["zzz"], prompt_chunk_ids=[])
    assert stage(t, doc(split), theta=0.9) == "chunk"
    assert stage(t, doc(split), theta=0.5) == "retrieve"


def test_index_failure_on_embedding_model_mismatch():
    assert stage(trace(query_embedding_model="embed-v2")) == "index"


def test_index_failure_when_covering_chunk_not_indexed():
    chunks = good_chunks()
    chunks[1] = fa.Chunk("c1", S, E, MODEL, indexed=False)
    assert stage(trace(), doc(chunks)) == "index"


def test_retrieve_failure_when_evidence_outside_top_k():
    assert stage(trace(retrieved_ids=["c0", "c2"])) == "retrieve"


def test_assemble_failure_when_dropped_from_prompt():
    assert stage(trace(prompt_chunk_ids=["c2"])) == "assemble"


def test_evidence_in_prompt_needs_human():
    assert stage(trace()) == fa.NEEDS_HUMAN


def test_unanswerable_answered_is_generate_fp1():
    a = fa.attribute(trace(gold_spans=[]), doc(good_chunks()))
    assert (a.stage, a.sub_label) == ("generate", "FP1")


def test_evidence_mode_all_vs_any():
    missing = fa.GoldSpan("d1", "v1", "This sentence does not exist anywhere in the document at all.")
    spans = [fa.GoldSpan("d1", "v1", SPAN), missing]
    assert stage(trace(gold_spans=spans, evidence_mode="all")) == "parse"
    assert stage(trace(gold_spans=spans, evidence_mode="any")) == fa.NEEDS_HUMAN


def test_security_items_excluded_from_distribution():
    traces = [trace(), trace(question_id="acl1", tags=["acl_probe"], correct=True)]
    report = fa.run(traces, doc(good_chunks()), {}, 0.5, 90.0)
    assert report["n_questions"] == 1
    assert report["security_items"][0]["question_id"] == "acl1"


def test_human_labels_resolve_and_validate(tmp_path):
    path = tmp_path / "labels.csv"
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["question_id", "stage", "sub_label"])
        w.writerow(["q1", "generate", "FP4"])
    report = fa.run([trace()], doc(good_chunks()), fa.load_labels(path), 0.5, 90.0)
    assert report["first_failing_stage"]["generate"] == 1
    assert report["generate_sub_labels"] == {"FP4": 1}

    bad = tmp_path / "bad.csv"
    bad.write_text("question_id,stage,sub_label\nq1,retrieve,\n")
    with pytest.raises(ValueError):
        fa.load_labels(bad)


def test_cli_end_to_end(tmp_path):
    docs = tmp_path / "docs.jsonl"
    docs.write_text(json.dumps({
        "doc_id": "d1", "doc_version": "v1", "text": TEXT,
        "chunks": [c.__dict__ for c in good_chunks()],
    }) + "\n")
    traces = tmp_path / "traces.jsonl"
    rows = [
        {"question_id": "q1", "workload_class": "large", "correct": False,
         "gold_spans": [{"doc_id": "d1", "doc_version": "v1", "text": SPAN}],
         "query_embedding_model": MODEL, "retrieved_ids": ["c0"], "prompt_chunk_ids": ["c0"]},
        {"question_id": "q2", "workload_class": "small", "correct": True},
    ]
    traces.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    out = tmp_path / "out.json"
    assert fa.main(["--traces", str(traces), "--docs", str(docs), "--out", str(out)]) == 0
    report = json.loads(out.read_text())
    assert report["first_failing_stage"]["retrieve"] == 1
    assert set(report["theta_sensitivity"]) == {"0.40", "0.50", "0.60"}
