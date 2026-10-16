#!/usr/bin/env python3
"""Git-friendly chunk store and disposable vector caches for a resource root.

Canonical state lives in ``store/state/chunks/``: one JSONL shard per indexed
file, named after its path (``<target_path>.jsonl``; very long names are
shortened with a hash). The first line is a header with the file's identity,
sha256, metadata and embedding model; each further line is one chunk with its
text and its embedding as base64 little-endian float16. A sync rewrites only
the shards of files that changed, so commits stay small and no file grows with
the whole corpus.

LanceDB (``store/lancedb``) and SQLite (``store/sqlite``) are local caches built
from the shards without re-embedding. Each cache records the content hash of the
shards it was built from; the hash is computed from the shard files on disk, so
a pull, merge or checkout that changes shards marks the caches stale. Caches are
never committed.

The pre-0.3 single file ``store/state/chunks.jsonl`` is migrated to shards,
keeping its embeddings; shards that already exist take precedence.
"""

from __future__ import annotations

import base64
import hashlib
import json
import shutil
import sqlite3
import struct
from pathlib import Path
from typing import Any, Iterable

FORMAT = "skillbag-chunk-shards/1"
VECTOR_ENCODING = "f16-le-base64"
SHARD_DIR = "chunks"
LEGACY = "chunks.jsonl"
CACHE_META = ".cache-meta.json"
HEADER_KEYS = ("resource_id", "target_path", "sha256", "metadata", "embedding_model")
MAX_SHARD_NAME_BYTES = 200
CACHE_IGNORES = ("store/lancedb/", "store/sqlite/")


def encode_vector(vector: Iterable[float]) -> str:
    values = [float(v) for v in vector]
    return base64.b64encode(struct.pack(f"<{len(values)}e", *values)).decode("ascii")


def decode_vector(text: str) -> list[float]:
    raw = base64.b64decode(text)
    return list(struct.unpack(f"<{len(raw) // 2}e", raw))


def shard_path(state_dir: Path, target_path: str) -> Path:
    rel = Path(target_path)
    name = f"{rel.name}.jsonl"
    if len(name.encode("utf-8")) > MAX_SHARD_NAME_BYTES:
        digest = hashlib.sha256(target_path.encode("utf-8")).hexdigest()[:16]
        stem = rel.name.encode("utf-8")[: MAX_SHARD_NAME_BYTES - 40].decode("utf-8", "ignore")
        name = f"{stem}~{digest}.jsonl"
    return state_dir / SHARD_DIR / rel.parent / name


def _dumps(row: dict[str, Any]) -> str:
    # Escape U+2028/U+2029 so every row is exactly one line for any reader.
    text = json.dumps(row, sort_keys=True, ensure_ascii=False)
    return text.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def shard_files(state_dir: Path) -> list[Path]:
    root = state_dir / SHARD_DIR
    return sorted(root.rglob("*.jsonl")) if root.exists() else []


def read_header(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        first = handle.readline()
    return json.loads(first) if first.strip() else {}


def shard_index(state_dir: Path) -> dict[str, dict[str, Any]]:
    """target_path -> {path, sha256, chunks} from shard headers (cheap: first line only)."""
    index = {}
    for path in shard_files(state_dir):
        header = read_header(path)
        if header.get("target_path"):
            index[header["target_path"]] = {"path": path, "sha256": header.get("sha256"), "chunks": header.get("chunks", 0)}
    return index


def read_shard(path: Path) -> list[dict[str, Any]]:
    lines = [line for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]
    if not lines:
        return []
    header = json.loads(lines[0])
    shared = {key: header.get(key) for key in HEADER_KEYS}
    rows = []
    for line in lines[1:]:
        row = {**shared, **json.loads(line)}
        encoded = row.pop("vector_f16", None)
        if encoded is not None:
            row["vector"] = decode_vector(encoded)
        rows.append(row)
    return rows


def read_chunks(state_dir: Path) -> list[dict[str, Any]]:
    """All chunk rows from shards; before migration, from the legacy single file. Never writes."""
    files = shard_files(state_dir)
    if files:
        rows: list[dict[str, Any]] = []
        for path in files:
            rows.extend(read_shard(path))
        return rows
    legacy = state_dir / LEGACY
    if legacy.exists():
        return [json.loads(line) for line in legacy.read_text(encoding="utf-8").split("\n") if line.strip()]
    return []


def content_hash(state_dir: Path) -> str:
    """Hash of every shard file's path and bytes, computed from disk."""
    digest = hashlib.sha256()
    root = state_dir / SHARD_DIR
    for path in shard_files(state_dir):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    legacy = state_dir / LEGACY
    if not shard_files(state_dir) and legacy.exists():
        digest.update(hashlib.sha256(legacy.read_bytes()).digest())
    return digest.hexdigest()


def write_shard(state_dir: Path, target_path: str, rows: list[dict[str, Any]]) -> Path | None:
    """Write one file's chunks; an empty list removes the shard. Unchanged content is not rewritten."""
    if not rows:
        delete_shard(state_dir, target_path)
        return None
    path = shard_path(state_dir, target_path)
    rows = sorted(rows, key=lambda r: int(r.get("chunk_index") or 0))
    first = rows[0]
    vectors = [r.get("vector") for r in rows if r.get("vector") is not None]
    header = {"format": FORMAT, "vector_encoding": VECTOR_ENCODING, "chunks": len(rows),
              "dim": len(vectors[0]) if vectors else None}
    header.update({key: first.get(key) for key in HEADER_KEYS})
    lines = [_dumps(header)]
    for row in rows:
        item = {k: v for k, v in row.items() if k not in HEADER_KEYS and k not in ("vector", "updated_at")}
        if row.get("vector") is not None:
            item["vector_f16"] = encode_vector(row["vector"])
        lines.append(_dumps(item))
    text = "\n".join(lines) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.write_text(text, encoding="utf-8")
    return path


def delete_shard(state_dir: Path, target_path: str, path: Path | None = None) -> None:
    path = path or shard_path(state_dir, target_path)
    if path.exists():
        path.unlink()
    root = state_dir / SHARD_DIR
    parent = path.parent
    while parent != root and parent.exists() and not any(parent.iterdir()):
        parent.rmdir()
        parent = parent.parent


def ensure_cache_ignores(resource_root: Path) -> bool:
    """Make sure the resource root's .gitignore keeps the local caches out of Git."""
    path = resource_root / ".gitignore"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    missing = [line for line in CACHE_IGNORES if line not in existing.splitlines()]
    if not missing:
        return False
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    path.write_text(existing + prefix + "\n".join(missing) + "\n", encoding="utf-8")
    return True


def migrate_legacy(state_dir: Path) -> dict[str, Any]:
    """Convert a legacy chunks.jsonl to shards, keeping embeddings. Existing shards win."""
    legacy = state_dir / LEGACY
    if not legacy.exists():
        return {"migrated": False}
    rows = [json.loads(line) for line in legacy.read_text(encoding="utf-8").split("\n") if line.strip()]
    existing = shard_index(state_dir)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["target_path"]), []).append(row)
    written = 0
    for target, group in grouped.items():
        if target in existing:
            continue
        write_shard(state_dir, target, group)
        written += 1
    legacy.unlink()
    ensure_cache_ignores(state_dir.parent.parent)
    return {"migrated": True, "files": written, "skipped_existing": len(grouped) - written, "chunks": len(rows)}


def save_chunks(
    state_dir: Path,
    new_rows: list[dict[str, Any]],
    changed_paths: set[str] | None,
    removed_paths: set[str],
) -> dict[str, Any]:
    """Update shards: drop removed files, then rewrite changed ones (all when changed_paths is None).

    Rows without a vector reuse the stored vector of the same chunk id, so a run
    without embedding never discards embeddings that are still valid.
    """
    migrate_legacy(state_dir)
    index = shard_index(state_dir)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in new_rows:
        grouped.setdefault(str(row["target_path"]), []).append(row)
    targets = set(grouped) if changed_paths is None else set(changed_paths)
    stale = set(removed_paths)
    if changed_paths is None:
        stale |= set(index) - targets
    # Delete first: on case- or normalization-insensitive file systems a rename can map
    # the removed and the added file to the same shard name.
    for target in stale - targets:
        if target in index:
            delete_shard(state_dir, target, index[target]["path"])
    for target in targets:
        rows = grouped.get(target, [])
        if rows and target in index and any(r.get("vector") is None for r in rows):
            previous = {r["id"]: r for r in read_shard(index[target]["path"])}
            for r in rows:
                old = previous.get(r["id"])
                if r.get("vector") is None and old and old.get("vector") is not None:
                    r["vector"] = old["vector"]
                    r["embedding_model"] = old.get("embedding_model")
        old_path = index[target]["path"] if target in index else None
        new_path = write_shard(state_dir, target, rows)
        if old_path is not None and old_path != new_path and old_path.exists() and (new_path is None or not old_path.samefile(new_path)):
            delete_shard(state_dir, target, old_path)
    ensure_cache_ignores(state_dir.parent.parent)
    files = shard_files(state_dir)
    return {"shards": len(files), "chunks": sum(int(read_header(p).get("chunks", 0)) for p in files),
            "content_hash": content_hash(state_dir)}


def _file_hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def cache_key(resource_root: Path, backend: str) -> dict[str, Any]:
    state_dir = resource_root / "store/state"
    key: dict[str, Any] = {"format": FORMAT, "content_hash": content_hash(state_dir)}
    if backend == "sqlite":
        key["file_state"] = _file_hash(state_dir / "file-state.jsonl")
        key["summaries"] = _file_hash(state_dir / "summaries.jsonl")
    return key


def stale_caches(resource_root: Path, backends: Iterable[str] = ("lancedb", "sqlite")) -> list[str]:
    stale = []
    for backend in backends:
        meta = resource_root / "store" / backend / CACHE_META
        current = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else None
        if current != cache_key(resource_root, backend):
            stale.append(backend)
    return stale


def _mark(resource_root: Path, backend: str, key: dict[str, Any]) -> None:
    meta = resource_root / "store" / backend / CACHE_META
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps(key, sort_keys=True) + "\n", encoding="utf-8")


def build_lancedb(resource_root: Path, rows: list[dict[str, Any]], key: dict[str, Any]) -> int:
    import lancedb  # optional dependency

    vector_rows = [row for row in rows if row.get("vector") is not None]
    path = resource_root / "store/lancedb"
    if path.exists():
        shutil.rmtree(path)  # disposable cache: a fresh build keeps no old table versions
    db = lancedb.connect(str(path))
    if vector_rows:
        db.create_table("chunks", data=vector_rows, mode="overwrite")
    _mark(resource_root, "lancedb", key)
    return len(vector_rows)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line.strip()]


def build_sqlite(resource_root: Path, chunks: list[dict[str, Any]], key: dict[str, Any]) -> Path:
    state_dir = resource_root / "store/state"
    resources = [r for r in _jsonl(state_dir / "file-state.jsonl") if r.get("status", "present") == "present"]
    summaries = _jsonl(state_dir / "summaries.jsonl")
    db_path = resource_root / "store/sqlite/resources.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "create table resources (id text primary key, target_path text not null, kind text not null, size integer not null,"
            " mtime_ns integer not null, sha256 text not null, metadata_json text not null, status text not null)"
        )
        conn.execute(
            "create table summaries (id text primary key, resource_id text not null, target_path text not null, kind text not null,"
            " title text not null, summary text not null, summary_backend text, summary_model text, summary_fallback_reason text,"
            " keywords_json text not null, metadata_json text not null, sha256 text not null, updated_at text not null)"
        )
        conn.execute(
            "create table chunks (id text primary key, resource_id text not null, target_path text not null, chunk_index integer not null,"
            " start_char integer not null, end_char integer not null, text text not null, metadata_json text not null, sha256 text not null,"
            " embedding_model text, row_index integer)"
        )
        conn.executemany(
            "insert or replace into resources values (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (r["id"], r["target_path"], r.get("kind", ""), int(r.get("size", 0)), int(r.get("mtime_ns", 0)), r.get("sha256", ""),
                 json.dumps(r.get("metadata", {}), sort_keys=True), r.get("status", "present"))
                for r in resources if r.get("id") and r.get("target_path")
            ],
        )
        conn.executemany(
            "insert or replace into summaries values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (r["id"], r["resource_id"], r["target_path"], r.get("kind", ""), r.get("title", ""), r.get("summary", ""),
                 r.get("summary_backend"), r.get("summary_model"), r.get("summary_fallback_reason"),
                 json.dumps(r.get("keywords", []), sort_keys=True), json.dumps(r.get("metadata", {}), sort_keys=True),
                 r.get("sha256", ""), r.get("updated_at", ""))
                for r in summaries
            ],
        )
        conn.executemany(
            "insert or replace into chunks values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (r["id"], r.get("resource_id", ""), r["target_path"], int(r.get("chunk_index") or 0), int(r.get("start_char") or 0),
                 int(r.get("end_char") or 0), r.get("text", ""), json.dumps(r.get("metadata", {}), sort_keys=True),
                 r.get("sha256", ""), r.get("embedding_model"), r.get("row_index"))
                for r in chunks
            ],
        )
        for statement in (
            "create index idx_resources_target_path on resources(target_path)",
            "create index idx_summaries_resource_id on summaries(resource_id)",
            "create index idx_summaries_target_path on summaries(target_path)",
            "create index idx_chunks_resource_id on chunks(resource_id)",
            "create index idx_chunks_target_path on chunks(target_path)",
        ):
            conn.execute(statement)
    with sqlite3.connect(db_path) as conn:
        conn.execute("vacuum")
    _mark(resource_root, "sqlite", key)
    return db_path


def rebuild_caches(
    resource_root: Path,
    backends: Iterable[str] = ("lancedb", "sqlite"),
    only_stale: bool = True,
) -> dict[str, Any]:
    """Build LanceDB and SQLite from store/state without re-embedding (migrating a legacy file first)."""
    state_dir = resource_root / "store/state"
    report: dict[str, Any] = {"migration": migrate_legacy(state_dir), "rebuilt": [], "warnings": []}
    targets = [b for b in backends if not only_stale or b in stale_caches(resource_root, [b])]
    report["content_hash"] = content_hash(state_dir)
    if not targets:
        return report
    rows = read_chunks(state_dir)
    without_vectors = sum(1 for r in rows if r.get("vector") is None)
    if without_vectors:
        report["warnings"].append(f"{without_vectors} of {len(rows)} chunks have no embedding; run a sync with --embed")
    if "lancedb" in targets:
        try:
            report["lancedb_vectors"] = build_lancedb(resource_root, rows, cache_key(resource_root, "lancedb"))
            report["rebuilt"].append("lancedb")
        except Exception as exc:  # optional dependency or build failure
            report["warnings"].append(f"lancedb: {exc}")
    if "sqlite" in targets:
        build_sqlite(resource_root, rows, cache_key(resource_root, "sqlite"))
        report["rebuilt"].append("sqlite")
    return report
