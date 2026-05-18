#!/usr/bin/env python3
"""Delta-scan a resource scaffold and optionally build local embeddings.

The script is intentionally local-first:
- tracks file state with size, mtime, and sha256
- applies configurable metadata defaults and path rules
- chunks text derivatives without asking the main agent to read them
- writes compact resource summaries for cheap later discovery
- optionally embeds chunks with a local Hugging Face SentenceTransformer
- optionally writes a LanceDB `chunks` table when lancedb is installed
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter
import fnmatch
import hashlib
import json
import re
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TEXT_SUFFIXES = {".md", ".txt", ".csv", ".json", ".jsonl", ".yaml", ".yml"}
DOCUMENT_TRANSCRIPT_SOURCE_SUFFIXES = {
    ".pdf",
    ".epub",
    ".docx",
    ".doc",
    ".odt",
    ".rtf",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".bmp",
    ".gif",
}
MEDIA_TRANSCRIPT_SOURCE_SUFFIXES = {
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".webm",
    ".m4v",
}
TRANSCRIPT_SOURCE_SUFFIXES = DOCUMENT_TRANSCRIPT_SOURCE_SUFFIXES | MEDIA_TRANSCRIPT_SOURCE_SUFFIXES
SCAN_ROOTS = [
    "sources/originals",
    "sources/external",
    "derivatives/transcripts",
    "derivatives/structured",
    "derivatives/media",
    "derivatives/normalized",
    "store/exports",
]
SOURCE_TRUTH_ROOTS = {
    "originals": ["sources/originals"],
    "all-sources": ["sources/originals", "sources/external"],
}
DERIVATIVE_ROOTS = [
    "derivatives/transcripts",
    "derivatives/structured",
    "derivatives/media",
    "derivatives/normalized",
]
SOURCE_CANDIDATE_SUFFIXES = sorted(TEXT_SUFFIXES | TRANSCRIPT_SOURCE_SUFFIXES)
STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "also",
    "because",
    "before",
    "between",
    "could",
    "from",
    "have",
    "into",
    "more",
    "should",
    "than",
    "that",
    "their",
    "there",
    "these",
    "this",
    "through",
    "under",
    "using",
    "when",
    "where",
    "which",
    "with",
    "would",
}


@dataclass
class FileRecord:
    id: str
    target_path: str
    kind: str
    size: int
    mtime_ns: int
    sha256: str
    metadata: dict[str, Any]
    status: str = "present"

    def as_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "target_path": self.target_path,
            "kind": self.kind,
            "size": self.size,
            "mtime_ns": self.mtime_ns,
            "sha256": self.sha256,
            "metadata": self.metadata,
            "status": self.status,
        }


@dataclass
class SummaryResult:
    text: str
    backend: str
    model: str | None = None
    fallback_reason: str | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def infer_kind(rel: Path) -> str:
    rel_text = rel.as_posix()
    if rel_text.startswith("sources/"):
        return "source"
    if rel_text.startswith("derivatives/transcripts/"):
        return "transcript"
    if rel_text.startswith("derivatives/structured/"):
        return "structured"
    if rel_text.startswith("derivatives/media/"):
        return "media-derivative"
    if rel_text.startswith("derivatives/normalized/"):
        return "normalized"
    if rel_text.startswith("store/exports/"):
        return "metadata-export"
    return "resource"


def infer_category(rel: Path) -> str | None:
    parts = rel.parts
    if "knowledge" in parts:
        idx = parts.index("knowledge")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def apply_metadata_profile(rel: Path, profile: dict[str, Any]) -> dict[str, Any]:
    rel_text = rel.as_posix()
    metadata = dict(profile.get("defaults", {}))
    category = infer_category(rel)
    if category:
        metadata.setdefault("category", category)

    suffix = rel.suffix.lower().lstrip(".")
    if suffix:
        metadata.setdefault("file_extension", suffix)

    for rule in profile.get("path_rules", []):
        pattern = rule.get("pattern")
        if pattern and fnmatch.fnmatch(rel_text, pattern):
            metadata.update(rule.get("metadata", {}))

    metadata.setdefault("source_path", rel_text)
    return metadata


def scan_files(resource_root: Path, profile: dict[str, Any]) -> list[FileRecord]:
    records: list[FileRecord] = []
    for scan_root in SCAN_ROOTS:
        root = resource_root / scan_root
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            rel = path.relative_to(resource_root)
            stat = path.stat()
            records.append(
                FileRecord(
                    id=stable_id(rel.as_posix()),
                    target_path=rel.as_posix(),
                    kind=infer_kind(rel),
                    size=stat.st_size,
                    mtime_ns=stat.st_mtime_ns,
                    sha256=sha256(path),
                    metadata=apply_metadata_profile(rel, profile),
                )
            )
    return records


def transcript_candidates(resource_root: Path, source_path: Path) -> list[Path]:
    rel = source_path.relative_to(resource_root)
    if not rel.as_posix().startswith("sources/originals/"):
        return []
    tail = Path(*rel.parts[2:])
    derivative_root = (
        "derivatives/media"
        if source_path.suffix.lower() in MEDIA_TRANSCRIPT_SOURCE_SUFFIXES
        else "derivatives/transcripts"
    )
    candidates = [
        resource_root / derivative_root / tail.with_suffix(".md"),
    ]
    parts = tail.parts
    if "raw" in parts:
        raw_idx = parts.index("raw")
        collapsed = Path(*parts[:raw_idx], *parts[raw_idx + 1:]).with_suffix(".md")
        candidates.insert(0, resource_root / derivative_root / collapsed)
    return candidates


def rel_under(rel_text: str, root: str) -> bool:
    return rel_text == root or rel_text.startswith(f"{root}/")


def is_derivative_path(rel_text: str) -> bool:
    return any(rel_under(rel_text, root) for root in DERIVATIVE_ROOTS)


def derivative_tail(rel: Path) -> Path | None:
    parts = rel.parts
    if len(parts) < 3 or parts[0] != "derivatives":
        return None
    return Path(*parts[2:])


def source_hints_from_derivative(path: Path, resource_root: Path) -> list[Path]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:4096]
    except OSError:
        return []
    if not text.startswith("---"):
        return []

    hints = []
    for line in text.splitlines()[1:80]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep and key.strip() in {"source_path", "original_path", "input_path"}:
            raw = value.strip().strip("'\"")
            if not raw:
                continue
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = resource_root / candidate
            try:
                candidate.relative_to(resource_root)
            except ValueError:
                continue
            hints.append(candidate)
    return hints


def display_path(path: Path, resource_root: Path) -> str:
    try:
        return str(path.relative_to(resource_root))
    except ValueError:
        return str(path)


def candidate_source_paths(
    resource_root: Path,
    derivative_path: Path,
    source_truth: str,
) -> list[Path]:
    rel = derivative_path.relative_to(resource_root)
    tail = derivative_tail(rel)
    if tail is None:
        return []

    source_roots = SOURCE_TRUTH_ROOTS[source_truth]
    candidates = []
    for candidate in source_hints_from_derivative(derivative_path, resource_root):
        rel_text = candidate.relative_to(resource_root).as_posix()
        if any(rel_under(rel_text, source_root) for source_root in source_roots):
            candidates.append(candidate)

    suffixes = [tail.suffix] if tail.suffix else []
    suffixes.extend(suffix for suffix in SOURCE_CANDIDATE_SUFFIXES if suffix not in suffixes)

    tail_variants = [tail]
    parts = tail.parts
    if "raw" not in parts and len(parts) >= 2:
        tail_variants.append(Path(*parts[:-1], "raw", parts[-1]))

    for source_root in source_roots:
        for variant in tail_variants:
            for suffix in suffixes:
                candidates.append(resource_root / source_root / variant.with_suffix(suffix))

    seen = set()
    unique = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(candidate)
    return unique


def filter_orphan_derivatives(
    resource_root: Path,
    records: list[FileRecord],
    policy: str,
    source_truth: str,
    apply: bool,
) -> tuple[list[FileRecord], dict[str, Any]]:
    if policy not in {"report", "hide", "prune"}:
        raise ValueError(f"unsupported orphan derivative policy: {policy}")
    if source_truth not in SOURCE_TRUTH_ROOTS:
        raise ValueError(f"unsupported source truth mode: {source_truth}")

    kept = []
    orphans = []
    pruned = []
    errors = []

    for record in records:
        rel_text = record.target_path
        if not is_derivative_path(rel_text):
            kept.append(record)
            continue

        path = resource_root / rel_text
        candidates = candidate_source_paths(resource_root, path, source_truth)
        existing_sources = [
            display_path(candidate, resource_root)
            for candidate in candidates
            if candidate.exists() and candidate.is_file()
        ]
        if existing_sources:
            kept.append(record)
            continue

        orphan = {
            "target_path": rel_text,
            "kind": record.kind,
            "candidate_sources": [
                display_path(candidate, resource_root)
                for candidate in candidates
            ][:12],
        }
        orphans.append(orphan)
        if policy == "report":
            kept.append(record)
            continue
        if policy == "prune" and apply:
            try:
                path.unlink()
                pruned.append(rel_text)
            except OSError as exc:
                errors.append({**orphan, "error": str(exc)})

    return kept, {
        "policy": policy,
        "source_truth": source_truth,
        "count": len(orphans),
        "hidden": 0 if policy == "report" else len(orphans) - len(errors),
        "pruned": len(pruned),
        "items": orphans[:100],
        "errors": errors,
    }


def find_existing_transcript(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def default_document_transcript_script() -> Path | None:
    # resource-sync-index/scripts/resource_sync_index.py ->
    # skillbag-resources/.skills/resource-sync-index/scripts -> skillbag
    workspace_root = Path(__file__).resolve().parents[4]
    script = (
        workspace_root
        / "skillbag-docs/.skills/document-to-markdown-transcript/scripts/document_to_markdown_transcript.py"
    )
    return script if script.exists() else None


def default_media_transcript_script() -> Path | None:
    # resource-sync-index/scripts/resource_sync_index.py ->
    # skillbag-resources/.skills/resource-sync-index/scripts -> skillbag
    workspace_root = Path(__file__).resolve().parents[4]
    script = (
        workspace_root
        / "skillbag-media/.skills/media-transcript/scripts/media_transcript.py"
    )
    return script if script.exists() else None


def media_language(language: str) -> str:
    if language.lower() in {"eng", "en"}:
        return "english"
    return language


def profile_transcript_command(profile: dict[str, Any]) -> list[str] | None:
    command = profile.get("transcripts", {}).get("processor_command")
    if not command:
        return None
    if isinstance(command, str):
        return command.split()
    if isinstance(command, list):
        return [str(part) for part in command]
    raise ValueError("transcripts.processor_command must be a string or list")


def build_transcript_command(
    command_template: list[str],
    source_path: Path,
    target_path: Path,
    language: str,
) -> list[str]:
    return [
        part.format(input=str(source_path), output=str(target_path), language=language)
        for part in command_template
    ]


def build_default_transcript_command(
    source_path: Path,
    target_path: Path,
    language: str,
    transcript_script: Path | None,
) -> tuple[list[str] | None, str | None]:
    if transcript_script is not None:
        return [
            "python3",
            str(transcript_script),
            str(source_path),
            str(target_path),
            "--language",
            language,
            "--overwrite",
        ], None

    if source_path.suffix.lower() in MEDIA_TRANSCRIPT_SOURCE_SUFFIXES:
        script = default_media_transcript_script()
        if script is None:
            return None, "no media-transcript processor found; install skillbag-media or configure transcripts.processor_command"
        return [
            "python3",
            str(script),
            "--input",
            str(source_path),
            "--output",
            str(target_path),
            "--language",
            media_language(language),
            "--backend",
            "hf",
            "--overwrite",
        ], None

    script = default_document_transcript_script()
    if script is None:
        return None, "no document-to-markdown transcript processor found; install skillbag-docs or configure transcripts.processor_command"
    return [
        "python3",
        str(script),
        str(source_path),
        str(target_path),
        "--language",
        language,
        "--overwrite",
    ], None


def ensure_transcripts(
    resource_root: Path,
    profile: dict[str, Any],
    policy: str,
    apply: bool,
    transcript_script: Path | None,
) -> dict[str, Any]:
    if policy == "skip":
        return {"policy": policy, "needed": 0, "generated": 0, "stale": 0, "missing": 0, "errors": []}

    records = []
    errors = []
    stale = 0
    missing = 0
    generated = 0
    language = profile.get("transcripts", {}).get("language", "eng")
    configured_command = profile_transcript_command(profile)

    for source_path in sorted((resource_root / "sources/originals").rglob("*")):
        if not source_path.is_file() or source_path.name.startswith("."):
            continue
        if source_path.suffix.lower() not in TRANSCRIPT_SOURCE_SUFFIXES:
            continue
        candidates = transcript_candidates(resource_root, source_path)
        existing = find_existing_transcript(candidates)
        target = existing or candidates[0]
        source_stat = source_path.stat()
        is_missing = existing is None
        is_stale = bool(existing and existing.stat().st_mtime_ns < source_stat.st_mtime_ns)

        should_generate = (
            policy == "force"
            or (policy in {"missing", "changed"} and is_missing)
            or (policy == "changed" and is_stale)
        )
        if is_missing:
            missing += 1
        if is_stale:
            stale += 1
        if not should_generate:
            continue

        record = {
            "source_path": str(source_path.relative_to(resource_root)),
            "target_path": str(target.relative_to(resource_root)),
            "reason": "missing" if is_missing else "stale" if is_stale else "force",
        }
        records.append(record)
        if not apply:
            continue
        if configured_command:
            command = build_transcript_command(configured_command, source_path, target, language)
        else:
            command, error = build_default_transcript_command(source_path, target, language, transcript_script)
            if command is None:
                errors.append({**record, "error": error or "no transcript processor command found"})
                continue
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            generated += 1
        except subprocess.CalledProcessError as exc:
            errors.append(
                {
                    **record,
                    "error": exc.stderr.strip() or exc.stdout.strip() or str(exc),
                }
            )

    return {
        "policy": policy,
        "needed": len(records),
        "generated": generated,
        "stale": stale,
        "missing": missing,
        "errors": errors,
    }


def diff_records(current: list[FileRecord], previous_rows: list[dict[str, Any]]) -> dict[str, Any]:
    previous = {
        row["target_path"]: row
        for row in previous_rows
        if row.get("status", "present") == "present" and "target_path" in row
    }
    current_by_path = {record.target_path: record for record in current}
    added, changed, unchanged = [], [], []

    for record in current:
        old = previous.get(record.target_path)
        if old is None:
            added.append(record)
        elif old.get("sha256") != record.sha256 or old.get("size") != record.size:
            changed.append(record)
        else:
            unchanged.append(record)

    removed = []
    for target_path, old in previous.items():
        if target_path not in current_by_path:
            old = dict(old)
            old["status"] = "removed"
            old["removed_at"] = utc_now()
            removed.append(old)

    return {
        "added": added,
        "changed": changed,
        "unchanged": unchanged,
        "removed": removed,
    }


def read_text(path: Path) -> str:
    return path.read_text(errors="ignore")


def is_text_index_candidate(record: FileRecord) -> bool:
    rel = Path(record.target_path)
    rel_text = rel.as_posix()
    return rel.suffix.lower() in TEXT_SUFFIXES and (
        record.kind in {"transcript", "structured", "media-derivative", "normalized", "metadata-export"}
        or rel_text.startswith("sources/originals/")
    )


def normalize_inline_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def text_title(path: Path, text: str) -> str:
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}#{1,3}\s+(.+?)\s*$", line)
        if match:
            return normalize_inline_text(match.group(1))[:160]
    return path.stem.replace("_", " ").replace("-", " ").strip() or path.name


def split_sentences(text: str) -> list[str]:
    normalized = normalize_inline_text(text)
    if not normalized:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip()]


def extract_keywords(text: str, limit: int) -> list[str]:
    words = [
        word.lower()
        for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text)
        if word.lower() not in STOPWORDS and not word.isdigit()
    ]
    return [word for word, _ in Counter(words).most_common(limit)]


def trim_summary(text: str, max_chars: int) -> str:
    normalized = normalize_inline_text(text)
    if len(normalized) <= max_chars:
        return normalized
    trimmed = normalized[: max_chars - 3].rsplit(" ", 1)[0].rstrip()
    return f"{trimmed}..."


def summarize_text_extractive(text: str, max_chars: int) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return trim_summary(text, max_chars)

    selected: list[str] = []
    for sentence in sentences:
        candidate = " ".join(selected + [sentence])
        if len(candidate) > max_chars:
            break
        selected.append(sentence)
        if len(selected) >= 4:
            break

    if not selected:
        return trim_summary(sentences[0], max_chars)
    return trim_summary(" ".join(selected), max_chars)


def clean_hf_summary_input(text: str, max_input_chars: int) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.startswith("---\n"):
        _, sep, rest = normalized.partition("\n---\n")
        if sep:
            normalized = rest
    normalized = re.sub(r"```.*?```", " ", normalized, flags=re.DOTALL)
    normalized = re.sub(r"`([^`]+)`", r"\1", normalized)
    normalized = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", normalized)
    normalized = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", normalized)
    normalized = re.sub(r"^\s{0,3}#{1,6}\s*", "", normalized, flags=re.MULTILINE)
    normalized = re.sub(r"^\s{0,3}[-*+]\s+", "- ", normalized, flags=re.MULTILINE)
    normalized = re.sub(r"\|", " ", normalized)
    normalized = normalize_inline_text(normalized)
    if len(normalized) <= max_input_chars:
        return normalized

    # Give the model the beginning plus a later slice instead of only the
    # opening boilerplate; this improves summaries for standards and policies.
    head_chars = max_input_chars * 2 // 3
    tail_chars = max_input_chars - head_chars
    head = normalized[:head_chars].rsplit(" ", 1)[0].strip()
    tail = normalized[-tail_chars:].split(" ", 1)[-1].strip()
    return normalize_inline_text(f"{head} {tail}")


class SummaryGenerator:
    def __init__(self, config: dict[str, Any]) -> None:
        self.backend = str(config.get("backend", config.get("mode", "huggingface"))).lower()
        self.model_name = str(config.get("model", "sshleifer/distilbart-cnn-12-6"))
        self.max_chars = int(config.get("max_chars", 900))
        self.max_input_chars = int(config.get("max_input_chars", 6000))
        self.min_input_words = int(config.get("min_input_words", 80))
        self.hf_max_length = int(config.get("hf_max_length", config.get("max_length_tokens", 180)))
        self.hf_min_length = int(config.get("hf_min_length", config.get("min_length_tokens", 40)))
        self.device = int(config.get("device", -1))
        self._pipeline = None
        self._load_error: str | None = None

    def _load_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline
        if self._load_error is not None:
            raise RuntimeError(self._load_error)
        try:
            from transformers import pipeline

            self._pipeline = pipeline(
                "summarization",
                model=self.model_name,
                tokenizer=self.model_name,
                device=self.device,
            )
            return self._pipeline
        except Exception as exc:  # pragma: no cover - optional dependency/runtime
            self._load_error = str(exc)
            raise

    def summarize(self, text: str) -> SummaryResult:
        if self.backend in {"extractive", "local-extractive"}:
            return SummaryResult(
                text=summarize_text_extractive(text, self.max_chars),
                backend="extractive",
            )

        cleaned = clean_hf_summary_input(text, self.max_input_chars)
        if len(cleaned.split()) < self.min_input_words:
            return SummaryResult(
                text=summarize_text_extractive(text, self.max_chars),
                backend="extractive",
                fallback_reason="short-input",
            )

        if self.backend not in {"huggingface", "hf", "auto"}:
            raise SystemExit(f"unsupported summary backend: {self.backend}")

        try:
            summarizer = self._load_pipeline()
            word_count = len(cleaned.split())
            max_length = min(self.hf_max_length, max(24, int(word_count * 0.55)))
            min_length = min(self.hf_min_length, max(8, max_length // 3))
            result = summarizer(
                cleaned,
                max_length=max_length,
                min_length=min_length,
                do_sample=False,
                truncation=True,
            )
            summary = result[0]["summary_text"] if result else ""
            if not summary.strip():
                raise RuntimeError("empty Hugging Face summary")
            return SummaryResult(
                text=trim_summary(summary, self.max_chars),
                backend="huggingface",
                model=self.model_name,
            )
        except Exception as exc:
            if self.backend == "auto":
                return SummaryResult(
                    text=summarize_text_extractive(text, self.max_chars),
                    backend="extractive",
                    model=self.model_name,
                    fallback_reason=str(exc),
                )
            raise SystemExit(f"Hugging Face summary generation failed: {exc}") from exc


def build_summary_rows(
    resource_root: Path,
    records: list[FileRecord],
    profile: dict[str, Any],
    existing_rows: list[dict[str, Any]],
    policy: str,
) -> list[dict[str, Any]]:
    if policy == "skip":
        return []

    config = profile.get("summaries", {})
    max_chars = int(config.get("max_chars", 900))
    keyword_limit = int(config.get("keyword_limit", 16))
    summary_generator = SummaryGenerator(config)
    existing_by_path = {
        row.get("target_path"): row
        for row in existing_rows
        if row.get("target_path")
    }

    rows = []
    for record in records:
        if not is_text_index_candidate(record):
            continue
        existing = existing_by_path.get(record.target_path)
        if policy in {"missing", "changed"} and existing and existing.get("sha256") == record.sha256:
            continue

        path = resource_root / record.target_path
        text = read_text(path)
        if not text.strip():
            continue
        summary = summary_generator.summarize(text)
        rows.append(
            {
                "id": stable_id(f"summary:{record.target_path}:{record.sha256}"),
                "resource_id": record.id,
                "target_path": record.target_path,
                "kind": record.kind,
                "title": text_title(path, text),
                "summary": trim_summary(summary.text, max_chars),
                "summary_backend": summary.backend,
                "summary_model": summary.model,
                "summary_fallback_reason": summary.fallback_reason,
                "keywords": extract_keywords(text, keyword_limit),
                "metadata": record.metadata,
                "sha256": record.sha256,
                "updated_at": utc_now(),
            }
        )
    return rows


def merge_summary_rows(
    existing_rows: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
    removed_paths: set[str],
) -> list[dict[str, Any]]:
    stale_paths = {row["target_path"] for row in new_rows} | removed_paths
    kept = [row for row in existing_rows if row.get("target_path") not in stale_paths]
    return kept + new_rows


def chunk_text(text: str, max_chars: int, overlap_chars: int) -> list[dict[str, Any]]:
    normalized = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not normalized:
        return []
    chunks = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + max_chars)
        if end < len(normalized):
            boundary = normalized.rfind("\n\n", start, end)
            if boundary > start + max_chars // 2:
                end = boundary
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append({"start_char": start, "end_char": end, "text": chunk})
        if end >= len(normalized):
            break
        start = max(0, end - overlap_chars)
    return chunks


def chunk_csv_rows(path: Path) -> list[dict[str, Any]]:
    chunks = []
    try:
        with path.open(newline="", encoding="utf-8-sig", errors="ignore") as f:
            rows = list(csv.reader(f))
    except csv.Error:
        return []
    if not rows:
        return []

    header = [normalize_inline_text(value) for value in rows[0]]
    for row_index, row in enumerate(rows[1:], start=2):
        if not any(value.strip() for value in row):
            continue
        pairs = []
        for idx, value in enumerate(row):
            value = normalize_inline_text(value)
            if not value:
                continue
            label = header[idx] if idx < len(header) and header[idx] else f"Column {idx + 1}"
            if value == label:
                continue
            pairs.append(f"{label}: {value}")
        if not pairs:
            continue
        text = "\n".join([f"CSV row: {row_index}", *pairs])
        chunks.append(
            {
                "start_char": row_index,
                "end_char": row_index,
                "text": text,
                "row_index": row_index,
            }
        )
    return chunks


def record_chunks(path: Path, max_chars: int, overlap_chars: int) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        csv_chunks = chunk_csv_rows(path)
        if csv_chunks:
            return csv_chunks
    return chunk_text(read_text(path), max_chars, overlap_chars)


def build_chunk_rows(
    resource_root: Path,
    records: list[FileRecord],
    profile: dict[str, Any],
    changed_paths: set[str] | None,
) -> list[dict[str, Any]]:
    chunking = profile.get("chunking", {})
    max_chars = int(chunking.get("max_chars", 1800))
    overlap_chars = int(chunking.get("overlap_chars", 250))
    rows = []
    for record in records:
        rel = Path(record.target_path)
        if changed_paths is not None and record.target_path not in changed_paths:
            continue
        if not is_text_index_candidate(record):
            continue
        path = resource_root / rel
        for idx, chunk in enumerate(record_chunks(path, max_chars, overlap_chars)):
            chunk_id = stable_id(f"{record.target_path}:{idx}:{record.sha256}")
            rows.append(
                {
                    "id": chunk_id,
                    "resource_id": record.id,
                    "target_path": record.target_path,
                    "chunk_index": idx,
                    "start_char": chunk["start_char"],
                    "end_char": chunk["end_char"],
                    "text": chunk["text"],
                    "metadata": record.metadata,
                    "sha256": record.sha256,
                    "updated_at": utc_now(),
                    "row_index": chunk.get("row_index"),
                }
            )
    return rows


def merge_chunk_rows(
    existing_rows: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
    changed_paths: set[str],
    removed_paths: set[str],
) -> list[dict[str, Any]]:
    stale_paths = changed_paths | removed_paths
    kept = [row for row in existing_rows if row.get("target_path") not in stale_paths]
    return kept + new_rows


def embed_rows(rows: list[dict[str, Any]], model_name: str) -> list[dict[str, Any]]:
    try:
        from sentence_transformers import SentenceTransformer
    except Exception as exc:  # pragma: no cover - dependency is optional
        raise SystemExit(f"sentence-transformers is required for --embed: {exc}")

    model = SentenceTransformer(model_name)
    texts = [row["text"] for row in rows]
    vectors = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
    for row, vector in zip(rows, vectors):
        row["vector"] = vector.tolist()
        row["embedding_model"] = model_name
    return rows


def write_lancedb(resource_root: Path, rows: list[dict[str, Any]]) -> None:
    try:
        import lancedb
    except Exception as exc:  # pragma: no cover - dependency is optional
        raise RuntimeError(f"lancedb is unavailable: {exc}") from exc

    db = lancedb.connect(str(resource_root / "store/lancedb"))
    if rows:
        db.create_table("chunks", data=rows, mode="overwrite")


def write_sqlite(
    resource_root: Path,
    resources: list[FileRecord],
    chunks: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
) -> Path:
    db_path = resource_root / "store/sqlite/resources.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("drop table if exists resources")
        conn.execute("drop table if exists summaries")
        conn.execute("drop table if exists chunks")
        conn.execute(
            """
            create table resources (
              id text primary key,
              target_path text not null,
              kind text not null,
              size integer not null,
              mtime_ns integer not null,
              sha256 text not null,
              metadata_json text not null,
              status text not null
            )
            """
        )
        conn.execute(
            """
            create table summaries (
              id text primary key,
              resource_id text not null,
              target_path text not null,
              kind text not null,
              title text not null,
              summary text not null,
              summary_backend text,
              summary_model text,
              summary_fallback_reason text,
              keywords_json text not null,
              metadata_json text not null,
              sha256 text not null,
              updated_at text not null
            )
            """
        )
        conn.execute(
            """
            create table chunks (
              id text primary key,
              resource_id text not null,
              target_path text not null,
              chunk_index integer not null,
              start_char integer not null,
              end_char integer not null,
              text text not null,
              metadata_json text not null,
              sha256 text not null,
              embedding_model text,
              vector_json text,
              updated_at text not null
            )
            """
        )
        conn.executemany(
            """
            insert into resources
            (id, target_path, kind, size, mtime_ns, sha256, metadata_json, status)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row.id,
                    row.target_path,
                    row.kind,
                    row.size,
                    row.mtime_ns,
                    row.sha256,
                    json.dumps(row.metadata, sort_keys=True),
                    row.status,
                )
                for row in resources
            ],
        )
        conn.executemany(
            """
            insert into summaries
            (id, resource_id, target_path, kind, title, summary, summary_backend,
             summary_model, summary_fallback_reason, keywords_json, metadata_json,
             sha256, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["id"],
                    row["resource_id"],
                    row["target_path"],
                    row["kind"],
                    row["title"],
                    row["summary"],
                    row.get("summary_backend"),
                    row.get("summary_model"),
                    row.get("summary_fallback_reason"),
                    json.dumps(row.get("keywords", []), sort_keys=True),
                    json.dumps(row["metadata"], sort_keys=True),
                    row["sha256"],
                    row["updated_at"],
                )
                for row in summaries
            ],
        )
        conn.executemany(
            """
            insert into chunks
            (id, resource_id, target_path, chunk_index, start_char, end_char, text,
             metadata_json, sha256, embedding_model, vector_json, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    row["id"],
                    row["resource_id"],
                    row["target_path"],
                    row["chunk_index"],
                    row["start_char"],
                    row["end_char"],
                    row["text"],
                    json.dumps(row["metadata"], sort_keys=True),
                    row["sha256"],
                    row.get("embedding_model"),
                    json.dumps(row.get("vector")) if row.get("vector") is not None else None,
                    row["updated_at"],
                )
                for row in chunks
            ],
        )
        conn.execute("create index idx_resources_target_path on resources(target_path)")
        conn.execute("create index idx_summaries_resource_id on summaries(resource_id)")
        conn.execute("create index idx_summaries_target_path on summaries(target_path)")
        conn.execute("create index idx_chunks_resource_id on chunks(resource_id)")
        conn.execute("create index idx_chunks_target_path on chunks(target_path)")
    return db_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resource-root", required=True, type=Path)
    parser.add_argument("--metadata-profile", type=Path)
    parser.add_argument("--mode", choices=["plan", "apply"], default="plan")
    parser.add_argument("--chunk-policy", choices=["changed-only", "all"], default="changed-only")
    parser.add_argument("--summary-policy", choices=["missing", "changed", "force", "skip"], default="missing")
    parser.add_argument("--transcript-policy", choices=["missing", "changed", "force", "skip"], default="missing")
    parser.add_argument("--transcript-script", type=Path)
    parser.add_argument("--source-truth", choices=["originals", "all-sources"])
    parser.add_argument("--orphan-derivative-policy", choices=["report", "hide", "prune"])
    parser.add_argument("--embed", action="store_true")
    parser.add_argument("--write-lancedb", action="store_true")
    parser.add_argument("--write-sqlite", action="store_true")
    parser.add_argument("--model")
    args = parser.parse_args()

    resource_root = args.resource_root
    transcript_script = None
    if args.transcript_script and str(args.transcript_script) != "auto":
        transcript_script = args.transcript_script
    profile_path = args.metadata_profile or resource_root / "metadata.profile.json"
    profile = read_json(profile_path)
    model_name = args.model or profile.get("embedding_model") or "sentence-transformers/all-MiniLM-L6-v2"
    sync_config = profile.get("sync", {})
    source_truth = args.source_truth or sync_config.get("source_truth", "originals")
    orphan_derivative_policy = (
        args.orphan_derivative_policy
        or sync_config.get("orphan_derivative_policy", "hide")
    )
    state_dir = resource_root / "store/state"
    file_state_path = state_dir / "file-state.jsonl"
    chunks_path = state_dir / "chunks.jsonl"
    summaries_path = state_dir / "summaries.jsonl"
    sync_runs_path = state_dir / "sync-runs.jsonl"

    transcript_report = ensure_transcripts(
        resource_root=resource_root,
        profile=profile,
        policy=args.transcript_policy,
        apply=args.mode == "apply",
        transcript_script=transcript_script,
    )

    current = scan_files(resource_root, profile)
    current, orphan_derivative_report = filter_orphan_derivatives(
        resource_root=resource_root,
        records=current,
        policy=orphan_derivative_policy,
        source_truth=source_truth,
        apply=args.mode == "apply",
    )
    previous_rows = read_jsonl(file_state_path)
    existing_summary_rows = read_jsonl(summaries_path)
    delta = diff_records(current, previous_rows)
    changed_paths = {r.target_path for r in delta["added"] + delta["changed"]}
    removed_paths = {r["target_path"] for r in delta["removed"] if "target_path" in r}
    chunk_filter = changed_paths if args.chunk_policy == "changed-only" else None
    summary_rows = build_summary_rows(
        resource_root=resource_root,
        records=current,
        profile=profile,
        existing_rows=existing_summary_rows,
        policy=args.summary_policy,
    )
    chunk_rows = build_chunk_rows(resource_root, current, profile, chunk_filter)

    report = {
        "resource_root": str(resource_root),
        "metadata_profile": str(profile_path),
        "mode": args.mode,
        "chunk_policy": args.chunk_policy,
        "summary_policy": args.summary_policy,
        "summary_backend": profile.get("summaries", {}).get("backend", "huggingface"),
        "summary_model": profile.get("summaries", {}).get("model", "sshleifer/distilbart-cnn-12-6"),
        "transcript_policy": args.transcript_policy,
        "source_truth": source_truth,
        "orphan_derivatives": orphan_derivative_report,
        "embedding_model": model_name,
        "transcripts": transcript_report,
        "counts": {
            "current": len(current),
            "added": len(delta["added"]),
            "changed": len(delta["changed"]),
            "unchanged": len(delta["unchanged"]),
            "removed": len(delta["removed"]),
            "orphan_derivatives": orphan_derivative_report["count"],
            "candidate_summaries": len(summary_rows),
            "candidate_chunks": len(chunk_rows),
        },
    }

    if args.mode == "apply":
        rows = [record.as_json() for record in current] + delta["removed"]
        write_jsonl(file_state_path, rows)
        final_summary_rows = merge_summary_rows(existing_summary_rows, summary_rows, removed_paths)
        report["counts"]["summaries"] = len(final_summary_rows)
        if summary_rows or removed_paths or args.summary_policy == "force":
            write_jsonl(summaries_path, final_summary_rows)
        if args.embed:
            chunk_rows = embed_rows(chunk_rows, model_name)
        if args.chunk_policy == "changed-only":
            final_chunk_rows = merge_chunk_rows(read_jsonl(chunks_path), chunk_rows, changed_paths, removed_paths)
        else:
            final_chunk_rows = chunk_rows
        if chunk_rows or removed_paths or args.chunk_policy == "all":
            write_jsonl(chunks_path, final_chunk_rows)
        written_backends = []
        backend_warnings = []
        if args.write_lancedb:
            if not args.embed:
                raise SystemExit("--write-lancedb requires --embed")
            try:
                write_lancedb(resource_root, final_chunk_rows)
                written_backends.append("lancedb")
            except Exception as exc:
                backend_warnings.append(str(exc))
                db_path = write_sqlite(resource_root, current, final_chunk_rows, final_summary_rows)
                written_backends.append(f"sqlite-fallback:{db_path}")
        if args.write_sqlite:
            db_path = write_sqlite(resource_root, current, final_chunk_rows, final_summary_rows)
            written_backends.append(f"sqlite:{db_path}")
        report["written_backends"] = written_backends
        if backend_warnings:
            report["backend_warnings"] = backend_warnings
        append_jsonl(sync_runs_path, {**report, "completed_at": utc_now()})

    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
