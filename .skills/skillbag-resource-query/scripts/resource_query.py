#!/usr/bin/env python3
"""Query a SkillBag resource root using local state files."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


STOPWORDS = {
    "about",
    "after",
    "against",
    "also",
    "and",
    "are",
    "for",
    "from",
    "how",
    "into",
    "not",
    "of",
    "or",
    "the",
    "this",
    "to",
    "what",
    "when",
    "where",
    "which",
    "with",
}
CONTROL_ID_RE = re.compile(r"\b\d+(?:\.\d+){1,}\b")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_filters(values: list[str]) -> dict[str, str]:
    filters = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"filter must use key=value syntax: {value}")
        key, val = value.split("=", 1)
        filters[key.strip()] = val.strip()
    return filters


def matches_filters(row: dict[str, Any], filters: dict[str, str]) -> bool:
    metadata = row.get("metadata") or {}
    for key, expected in filters.items():
        actual = row.get(key, metadata.get(key))
        if actual is None or str(actual).lower() != expected.lower():
            return False
    return True


def keyword_score(text: str, terms: list[str]) -> int:
    lower = text.lower()
    score = 0
    for term in terms:
        if CONTROL_ID_RE.fullmatch(term):
            score += 50 * len(re.findall(rf"(?<!\d){re.escape(term)}(?!\d)", lower))
        elif any(char.isdigit() for char in term) and any(char.isalpha() for char in term):
            count = len(re.findall(rf"\b{re.escape(term)}\b", lower))
            if count:
                score += 25 + min(count - 1, 2)
        else:
            count = len(re.findall(rf"\b{re.escape(term)}\b", lower))
            if count:
                score += 15 + min(count - 1, 2)
    return score


def query_terms(query: str) -> list[str]:
    lowered = query.lower()
    terms = CONTROL_ID_RE.findall(lowered)
    lowered_without_control_ids = CONTROL_ID_RE.sub(" ", lowered)
    for term in re.findall(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", lowered_without_control_ids):
        if term in STOPWORDS:
            continue
        if term.isdigit():
            continue
        if len(term) < 3:
            continue
        terms.append(term)
    return terms


def source_record_index(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_id = {row.get("id"): row for row in records if row.get("id")}
    by_path = {row.get("target_path"): row for row in records if row.get("target_path")}
    return {**by_id, **by_path}


def structural_keyword_bonus(row: dict[str, Any]) -> int:
    bonus = 0
    if row.get("row_index") is not None:
        bonus += 10
    if str(row.get("target_path", "")).startswith("sources/originals/"):
        bonus += 5
    return bonus


def encode_query(query: str, model_name: str) -> list[float]:
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:  # pragma: no cover - optional dependency
        raise SystemExit(f"sentence-transformers is required for vector search: {exc}")

    model = SentenceTransformer(model_name)
    return model.encode([query], normalize_embeddings=True)[0].tolist()


def vector_score(distance: float | int | None) -> float:
    if distance is None:
        return 0.0
    return round(100.0 / (1.0 + float(distance)), 4)


def vector_rows_from_lancedb(
    root: Path,
    query_vector: list[float],
    top_k: int,
    filters: dict[str, str],
    source_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    try:
        import lancedb
    except Exception:
        return []

    try:
        table = lancedb.connect(str(root / "store/lancedb")).open_table("chunks")
        raw_rows = table.search(query_vector).limit(max(top_k * 20, 50)).to_list()
    except Exception:
        return []

    rows = []
    for row in raw_rows:
        if not matches_filters(row, filters):
            continue
        source = source_index.get(row.get("resource_id")) or source_index.get(row.get("target_path")) or {}
        excerpt = re.sub(r"\s+", " ", str(row.get("text", ""))).strip()[:500]
        rows.append(
            {
                "score": vector_score(row.get("_distance")),
                "distance": row.get("_distance"),
                "match_type": "vector",
                "target_path": row.get("target_path"),
                "source_path": source.get("target_path"),
                "chunk_index": row.get("chunk_index"),
                "row_index": row.get("row_index"),
                "excerpt": excerpt,
                "metadata": row.get("metadata", {}),
            }
        )
        if len(rows) >= top_k:
            break
    return rows


def vector_rows_from_jsonl(
    chunks: list[dict[str, Any]],
    query_vector: list[float],
    top_k: int,
    filters: dict[str, str],
    source_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for row in chunks:
        if not matches_filters(row, filters):
            continue
        vector = row.get("vector")
        if not vector:
            continue
        score = sum(float(a) * float(b) for a, b in zip(query_vector, vector))
        source = source_index.get(row.get("resource_id")) or source_index.get(row.get("target_path")) or {}
        excerpt = re.sub(r"\s+", " ", row.get("text", "")).strip()[:500]
        rows.append(
            {
                "score": round(score * 100, 4),
                "match_type": "vector-jsonl",
                "target_path": row.get("target_path"),
                "source_path": source.get("target_path"),
                "chunk_index": row.get("chunk_index"),
                "row_index": row.get("row_index"),
                "excerpt": excerpt,
                "metadata": row.get("metadata", {}),
            }
        )
    rows.sort(key=lambda row: (-float(row.get("score") or 0), str(row.get("target_path") or "")))
    return rows[:top_k]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-root", required=True, type=Path)
    parser.add_argument("--query", required=True)
    parser.add_argument("--mode", choices=("metadata", "keyword", "vector", "hybrid"), default="hybrid")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--filter", action="append", default=[])
    args = parser.parse_args()

    root = args.resource_root.resolve()
    state_root = root / "store/state"
    profile = read_json(root / "metadata.profile.json")
    model_name = profile.get("embedding_model", "sentence-transformers/all-MiniLM-L6-v2")
    resources = read_jsonl(state_root / "file-state.jsonl")
    summaries = read_jsonl(state_root / "summaries.jsonl")
    chunks = read_jsonl(state_root / "chunks.jsonl")
    filters = parse_filters(args.filter)
    terms = query_terms(args.query)

    results = []
    source_index = source_record_index(resources)

    if args.mode in {"metadata", "hybrid"}:
        for row in resources:
            if row.get("status", "present") != "present":
                continue
            if not matches_filters(row, filters):
                continue
            searchable = " ".join(
                [
                    str(row.get("target_path", "")),
                    json.dumps(row.get("metadata", {}), sort_keys=True),
                ]
            )
            score = keyword_score(searchable, terms) if terms else 1
            if args.mode == "metadata" or score > 0:
                results.append(
                    {
                        "score": score,
                        "match_type": "metadata",
                        "target_path": row.get("target_path"),
                        "kind": row.get("kind"),
                        "metadata": row.get("metadata", {}),
                    }
                )

    if args.mode in {"keyword", "hybrid"}:
        for row in summaries:
            if not matches_filters(row, filters):
                continue
            searchable = " ".join(
                [
                    str(row.get("title", "")),
                    str(row.get("summary", "")),
                    " ".join(str(keyword) for keyword in row.get("keywords", [])),
                    json.dumps(row.get("metadata", {}), sort_keys=True),
                ]
            )
            score = keyword_score(searchable, terms)
            if score <= 0:
                continue
            source = source_index.get(row.get("resource_id")) or source_index.get(row.get("target_path")) or {}
            results.append(
                {
                    "score": score + 2,
                    "match_type": "summary",
                    "target_path": row.get("target_path"),
                    "source_path": source.get("target_path"),
                    "title": row.get("title"),
                    "summary": row.get("summary"),
                    "keywords": row.get("keywords", []),
                    "metadata": row.get("metadata", {}),
                }
            )

        for row in chunks:
            if not matches_filters(row, filters):
                continue
            text = row.get("text", "")
            searchable = " ".join(
                [
                    str(row.get("target_path", "")),
                    text,
                    json.dumps(row.get("metadata", {}), sort_keys=True),
                ]
            )
            score = keyword_score(searchable, terms)
            if score <= 0:
                continue
            source = source_index.get(row.get("resource_id")) or source_index.get(row.get("target_path")) or {}
            excerpt = re.sub(r"\s+", " ", text).strip()[:500]
            results.append(
                {
                    "score": score + structural_keyword_bonus(row),
                    "match_type": "chunk",
                    "target_path": row.get("target_path"),
                    "source_path": source.get("target_path"),
                    "chunk_index": row.get("chunk_index"),
                    "row_index": row.get("row_index"),
                    "excerpt": excerpt,
                    "metadata": row.get("metadata", {}),
                }
            )

    if args.mode in {"vector", "hybrid"}:
        query_vector = encode_query(args.query, model_name)
        vector_rows = vector_rows_from_lancedb(root, query_vector, args.top_k, filters, source_index)
        if not vector_rows:
            vector_rows = vector_rows_from_jsonl(chunks, query_vector, args.top_k, filters, source_index)
        results.extend(vector_rows)

    results.sort(key=lambda row: (-float(row.get("score") or 0), str(row.get("target_path") or "")))
    output = {
        "resource_root": str(root),
        "query": args.query,
        "mode": args.mode,
        "embedding_model": model_name if args.mode in {"vector", "hybrid"} else None,
        "searched": {
            "resources": len(resources),
            "summaries": len(summaries),
            "chunks": len(chunks),
        },
        "count": min(len(results), args.top_k),
        "results": results[: args.top_k],
    }
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
