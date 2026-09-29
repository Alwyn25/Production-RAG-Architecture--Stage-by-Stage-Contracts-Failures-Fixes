"""First-failing-stage attribution for wrong RAG answers (post-00 audit).

Walks the pipeline in order and returns the first stage whose check fails:

    system -> parse -> chunk -> index -> retrieve -> assemble -> (generate | cite)

Every check up to `assemble` is deterministic and uses span-level gold evidence.
Items whose evidence reached the prompt are marked `needs_human`; a human label
(generate or cite, optionally a Barnett FP4-FP7 sub-label) resolves them.

Inputs are produced by the post-01 baseline run on the eval v1 dev split; see
README.md in this directory for the schemas.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from rapidfuzz import fuzz

STAGES = ["system", "parse", "chunk", "index", "retrieve", "assemble", "generate", "cite"]
DETERMINISTIC = STAGES[:6]
HUMAN_STAGES = {"generate", "cite"}
GENERATE_SUBLABELS = {"FP4", "FP5", "FP6", "FP7"}  # Barnett et al. 2024
SECURITY_TAGS = {"acl_probe", "injection"}
NEEDS_HUMAN = "needs_human"


# ---------------------------------------------------------------- data model

@dataclass(frozen=True)
class GoldSpan:
    doc_id: str
    doc_version: str
    text: str  # gold evidence text; located in parsed text, so source offsets are not needed here


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    char_start: int  # offsets into the parsed document text
    char_end: int
    embedding_model: str
    indexed: bool = True


@dataclass
class ParsedDoc:
    doc_id: str
    doc_version: str
    text: str
    chunks: list[Chunk]


@dataclass
class Trace:
    question_id: str
    workload_class: str
    correct: bool
    tags: list[str] = field(default_factory=list)
    error: str | None = None
    refused: bool = False
    evidence_mode: str = "all"  # "all": every span needed (multi-hop); "any": one span suffices
    gold_spans: list[GoldSpan] = field(default_factory=list)
    query_embedding_model: str = ""
    retrieved_ids: list[str] = field(default_factory=list)
    prompt_chunk_ids: list[str] = field(default_factory=list)  # present and untruncated in the prompt


@dataclass
class Attribution:
    question_id: str
    workload_class: str
    stage: str  # one of STAGES or NEEDS_HUMAN
    evidence: str
    sub_label: str | None = None


# ---------------------------------------------------------------- span location

_WS = re.compile(r"\s+")


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Lowercase and collapse whitespace; return normalized text and a map to raw offsets."""
    out: list[str] = []
    index: list[int] = []
    prev_space = True
    for i, ch in enumerate(text):
        if ch.isspace():
            if not prev_space:
                out.append(" ")
                index.append(i)
            prev_space = True
        else:
            out.append(ch.lower())
            index.append(i)
            prev_space = False
    if out and out[-1] == " ":
        out.pop()
        index.pop()
    return "".join(out), index


def locate_span(span_text: str, parsed_text: str, min_similarity: float) -> tuple[int, int] | None:
    """Return raw (start, end) of the gold span in parsed text, or None if parsing lost it.

    Exact match on normalized text first; fuzzy alignment (rapidfuzz) as fallback so
    minor extraction noise (hyphenation, ligatures) doesn't count as a parse failure.
    """
    needle = _WS.sub(" ", span_text.strip().lower())
    if not needle:
        return None
    hay, raw = normalize_with_map(parsed_text)
    pos = hay.find(needle)
    if pos >= 0:
        return raw[pos], raw[pos + len(needle) - 1] + 1
    aln = fuzz.partial_ratio_alignment(needle, hay)
    if aln is None or aln.score < min_similarity or aln.dest_end <= aln.dest_start:
        return None
    return raw[aln.dest_start], raw[aln.dest_end - 1] + 1


def coverage(chunk: Chunk, start: int, end: int) -> float:
    """Share of the located gold span that falls inside the chunk."""
    overlap = max(0, min(chunk.char_end, end) - max(chunk.char_start, start))
    return overlap / (end - start)


# ---------------------------------------------------------------- cascade

def _span_stage(
    span: GoldSpan,
    trace: Trace,
    docs: dict[tuple[str, str], ParsedDoc],
    theta: float,
    min_similarity: float,
) -> tuple[str | None, str]:
    """First failing deterministic stage for one gold span (None = reached the prompt)."""
    doc = docs.get((span.doc_id, span.doc_version))
    if doc is None:
        return "parse", f"{span.doc_id}@{span.doc_version} missing from parsed corpus"
    loc = locate_span(span.text, doc.text, min_similarity)
    if loc is None:
        return "parse", f"gold span not found in parsed text of {span.doc_id}"
    covering = [c for c in doc.chunks if coverage(c, *loc) >= theta]
    if not covering:
        best = max((coverage(c, *loc) for c in doc.chunks), default=0.0)
        return "chunk", f"no chunk covers >= {theta:.2f} of span (best {best:.2f})"
    usable = [c for c in covering if c.indexed and c.embedding_model == trace.query_embedding_model]
    if not usable:
        return "index", (
            f"covering chunks not indexed or embedded with a different model "
            f"(query={trace.query_embedding_model})"
        )
    ids = {c.chunk_id for c in usable}
    if not ids & set(trace.retrieved_ids):
        return "retrieve", f"covering chunks {sorted(ids)} not in top-{len(trace.retrieved_ids)}"
    if not ids & set(trace.prompt_chunk_ids):
        return "assemble", "covering chunk retrieved but absent or truncated in prompt"
    return None, "evidence reached the prompt"


def attribute(
    trace: Trace,
    docs: dict[tuple[str, str], ParsedDoc],
    theta: float = 0.5,
    min_similarity: float = 90.0,
) -> Attribution | None:
    """Attribute one wrong answer. Returns None for correct answers."""
    if trace.correct:
        return None
    qid, wc = trace.question_id, trace.workload_class
    if trace.error:
        return Attribution(qid, wc, "system", trace.error)
    if not trace.gold_spans:  # unanswerable item that was answered (Barnett FP1)
        if trace.refused:
            return Attribution(qid, wc, NEEDS_HUMAN, "refused but marked wrong; check label")
        return Attribution(qid, wc, "generate", "unanswerable question answered", "FP1")

    results = [_span_stage(s, trace, docs, theta, min_similarity) for s in trace.gold_spans]
    order = {s: i for i, s in enumerate(STAGES)}
    rank = lambda r: order[r[0]] if r[0] is not None else len(STAGES)  # noqa: E731
    # "all": the answer fails as soon as any needed span is lost -> earliest failure.
    # "any": one surviving span is enough -> the span that got furthest decides.
    stage, evidence = (min if trace.evidence_mode == "all" else max)(results, key=rank)
    if stage is None:
        return Attribution(qid, wc, NEEDS_HUMAN, evidence)
    return Attribution(qid, wc, stage, evidence)


def apply_human_labels(items: list[Attribution], labels: dict[str, tuple[str, str | None]]) -> None:
    for a in items:
        if a.stage != NEEDS_HUMAN or a.question_id not in labels:
            continue
        stage, sub = labels[a.question_id]
        a.stage, a.sub_label = stage, sub
        a.evidence += " | human label"


# ---------------------------------------------------------------- io

def load_docs(path: Path) -> dict[tuple[str, str], ParsedDoc]:
    docs: dict[tuple[str, str], ParsedDoc] = {}
    for row in _jsonl(path):
        chunks = [Chunk(**c) for c in row["chunks"]]
        docs[(row["doc_id"], row["doc_version"])] = ParsedDoc(
            row["doc_id"], row["doc_version"], row["text"], chunks
        )
    return docs


def load_traces(path: Path) -> list[Trace]:
    traces = []
    for row in _jsonl(path):
        row["gold_spans"] = [GoldSpan(**s) for s in row.get("gold_spans", [])]
        traces.append(Trace(**row))
    return traces


def load_labels(path: Path | None) -> dict[str, tuple[str, str | None]]:
    if path is None:
        return {}
    labels: dict[str, tuple[str, str | None]] = {}
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            stage = row["stage"].strip()
            sub = (row.get("sub_label") or "").strip() or None
            if stage not in HUMAN_STAGES:
                raise ValueError(f"{row['question_id']}: human stage must be generate or cite, got {stage!r}")
            if sub and (stage != "generate" or sub not in GENERATE_SUBLABELS):
                raise ValueError(f"{row['question_id']}: sub_label {sub!r} only valid as FP4-FP7 on generate")
            labels[row["question_id"].strip()] = (stage, sub)
    return labels


def _jsonl(path: Path) -> Iterable[dict]:
    with path.open() as f:
        for n, line in enumerate(f, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    raise ValueError(f"{path}:{n}: {e}") from e


# ---------------------------------------------------------------- report

def run(
    traces: list[Trace],
    docs: dict[tuple[str, str], ParsedDoc],
    labels: dict[str, tuple[str, str | None]],
    theta: float,
    min_similarity: float,
) -> dict:
    quality = [t for t in traces if not SECURITY_TAGS & set(t.tags)]
    security = [t for t in traces if SECURITY_TAGS & set(t.tags)]
    items = [a for t in quality if (a := attribute(t, docs, theta, min_similarity))]
    apply_human_labels(items, labels)

    by_class: dict[str, Counter] = defaultdict(Counter)
    for a in items:
        by_class[a.workload_class][a.stage] += 1
    overall = Counter(a.stage for a in items)
    totals = Counter(t.workload_class for t in quality)
    return {
        "theta": theta,
        "min_similarity": min_similarity,
        "n_questions": len(quality),
        "n_wrong": len(items),
        "n_needs_human": overall.get(NEEDS_HUMAN, 0),
        "questions_per_class": dict(totals),
        "first_failing_stage": {s: overall.get(s, 0) for s in STAGES + [NEEDS_HUMAN]},
        "first_failing_stage_by_class": {
            wc: {s: c.get(s, 0) for s in STAGES + [NEEDS_HUMAN]} for wc, c in sorted(by_class.items())
        },
        "generate_sub_labels": dict(Counter(a.sub_label for a in items if a.sub_label)),
        "security_items": [
            {"question_id": t.question_id, "tags": t.tags, "correct": t.correct} for t in security
        ],
        "items": [a.__dict__ for a in items],
    }


def sensitivity(traces, docs, labels, thetas: list[float], min_similarity: float) -> dict:
    """Stage counts per theta; theta mainly moves items between chunk and retrieve."""
    return {
        f"{th:.2f}": run(traces, docs, labels, th, min_similarity)["first_failing_stage"]
        for th in thetas
    }


def markdown_table(report: dict) -> str:
    stages = [s for s in STAGES + [NEEDS_HUMAN] if report["first_failing_stage"].get(s)]
    head = "| class | n wrong | " + " | ".join(stages) + " |"
    sep = "|---" * (len(stages) + 2) + "|"
    rows = [head, sep]
    for wc, c in report["first_failing_stage_by_class"].items():
        rows.append(f"| {wc} | {sum(c.values())} | " + " | ".join(str(c.get(s, 0)) for s in stages) + " |")
    o = report["first_failing_stage"]
    rows.append(f"| **all** | {report['n_wrong']} | " + " | ".join(str(o.get(s, 0)) for s in stages) + " |")
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--traces", type=Path, required=True, help="per-question traces (JSONL)")
    p.add_argument("--docs", type=Path, required=True, help="parsed documents with chunks (JSONL)")
    p.add_argument("--labels", type=Path, help="human labels for needs_human items (CSV)")
    p.add_argument("--out", type=Path, default=Path(__file__).with_name("failure_attribution.json"))
    p.add_argument("--theta", type=float, default=0.5, help="span-coverage threshold for a chunk hit")
    p.add_argument("--min-similarity", type=float, default=90.0, help="fuzzy match floor (0-100)")
    p.add_argument("--sensitivity", type=float, nargs="*", default=[0.4, 0.5, 0.6])
    args = p.parse_args(argv)

    traces, docs = load_traces(args.traces), load_docs(args.docs)
    labels = load_labels(args.labels)
    report = run(traces, docs, labels, args.theta, args.min_similarity)
    if args.sensitivity:
        report["theta_sensitivity"] = sensitivity(traces, docs, labels, args.sensitivity, args.min_similarity)
    args.out.write_text(json.dumps(report, indent=2) + "\n")

    print(markdown_table(report))
    if report["n_needs_human"]:
        print(f"\n{report['n_needs_human']} item(s) need a human label (generate | cite).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
