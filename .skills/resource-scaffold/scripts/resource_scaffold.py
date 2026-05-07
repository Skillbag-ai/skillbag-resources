#!/usr/bin/env python3
"""Create or validate a portable SkillBag resource root."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


DIRECTORIES = [
    "sources/originals",
    "sources/external",
    "derivatives/transcripts",
    "derivatives/structured",
    "derivatives/media",
    "derivatives/normalized",
    "store/lancedb",
    "store/sqlite",
    "store/state",
    "store/exports",
    "staging/incoming",
    "staging/quarantine",
]

STATE_FILES = [
    "store/state/file-state.jsonl",
    "store/state/ingest-runs.jsonl",
    "store/state/sync-runs.jsonl",
    "store/state/summaries.jsonl",
    "store/state/chunks.jsonl",
]


def write_if_missing(path: Path, content: str, overwrite: bool) -> bool:
    if path.exists() and not overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def resource_yaml(name: str, purpose: str, backend: str, embedding_model: str) -> str:
    created_at = datetime.now(timezone.utc).isoformat()
    return f"""version: 1
name: {name}
created_at: {created_at}
purpose: {purpose}
backend: {backend}
embedding_model: {embedding_model}
source_roots:
  originals: sources/originals
  external: sources/external
derivative_roots:
  transcripts: derivatives/transcripts
  structured: derivatives/structured
  media: derivatives/media
  normalized: derivatives/normalized
store_root: store
state_root: store/state
"""


def metadata_profile(purpose: str, embedding_model: str) -> str:
    profile = {
        "embedding_model": embedding_model,
        "defaults": {
            "resource_purpose": purpose,
        },
        "embeddings": {
            "policy": "on-ingest",
            "write_lancedb": True,
            "write_sqlite": True,
        },
        "path_rules": [],
        "chunking": {
            "max_chars": 1800,
            "overlap_chars": 250,
        },
        "summaries": {
            "backend": "huggingface",
            "model": "sshleifer/distilbart-cnn-12-6",
            "max_chars": 900,
            "max_input_chars": 6000,
            "hf_min_length": 40,
            "hf_max_length": 180,
            "keyword_limit": 16,
        },
        "sync": {
            "source_truth": "originals",
            "orphan_derivative_policy": "hide",
        },
        "transcripts": {
            "language": "eng",
            "policy": "missing",
            "processor_preference": [
                "document-to-markdown-transcript",
                "extract-structured-tables",
                "media-transcript",
            ],
        },
    }
    return json.dumps(profile, indent=2, sort_keys=True) + "\n"


def readme(name: str, purpose: str) -> str:
    return f"""# {name}

This folder is a local SkillBag resource root.

## Purpose

{purpose}

- Put canonical copied source files under `sources/originals/`.
- Put external pointers or manifests under `sources/external/`.
- Put generated transcripts and structured derivatives under `derivatives/`.
- Resource state, chunks, and optional vector stores live under `store/`.
- Use `resource-sync-index` to refresh state and indexes.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-root", required=True, type=Path)
    parser.add_argument("--name")
    parser.add_argument("--purpose")
    parser.add_argument("--backend", default="lancedb")
    parser.add_argument("--embedding-model", default="sentence-transformers/all-MiniLM-L6-v2")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    root = args.resource_root.resolve()
    creating_config = args.overwrite or not (root / "resource.yaml").exists()
    if creating_config and not args.purpose:
        parser.error("--purpose is required when creating or overwriting a resource root")
    purpose = args.purpose or "See existing resource.yaml and README.md."
    name = args.name or root.name
    root.mkdir(parents=True, exist_ok=True)

    created_dirs = []
    for rel in DIRECTORIES:
        path = root / rel
        if not path.exists():
            created_dirs.append(rel)
        path.mkdir(parents=True, exist_ok=True)

    written_files = []
    files = {
        "resource.yaml": resource_yaml(name, purpose, args.backend, args.embedding_model),
        "metadata.profile.json": metadata_profile(purpose, args.embedding_model),
        "README.md": readme(name, purpose),
    }
    for rel, content in files.items():
        if write_if_missing(root / rel, content, args.overwrite):
            written_files.append(rel)

    for rel in STATE_FILES:
        path = root / rel
        if not path.exists() or args.overwrite:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
            written_files.append(rel)

    print(
        json.dumps(
            {
                "resource_root": str(root),
                "created_dirs": created_dirs,
                "written_files": written_files,
                "status": "ok",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
