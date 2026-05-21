# Changelog

## 0.2.0

- Renamed the public resource skills from `resource-*` to
  `skillbag-resource-*` and updated the catalog, dependencies, examples, and
  documentation references to the canonical Skillbag-ai prefix.

## 0.1.1

- Added EPUB originals to `skillbag-resource-sync-index` document transcript discovery
  so they can be converted through `skillbag-docs` and embedded when `pandoc`
  is available.

## 0.1.0

- Initial resource skillbag scaffold.
- Added base resource scaffold, ingestion, sync/index, and query skill
  proposals.
- Added bundled resource sync/index delta script with optional local Hugging
  Face embeddings, LanceDB output, and SQLite fallback storage.
- Added bundled scaffold and query helper scripts.
- Added row-level CSV chunking for structured tables, standards, and control
  matrices.
- Improved `skillbag-resource-query` so metadata, keyword, vector, and hybrid modes
  return candidate evidence that agents must inspect rather than treat as an
  oracle.
- Added exact/control-identifier-aware query scoring for standards and
  regulation lookups.
- Merged clean and dirty resource ingestion into one `skillbag-resource-ingest` skill
  with classification policy parameters.
- Moved resource summary generation into `skillbag-resource-sync-index` and added
  `summaries.jsonl` as the cheap discovery layer used by `skillbag-resource-query`.
- Switched default summary generation to a local Hugging Face summarization
  backend with extractive fallback available through profile configuration.
- Clarified that `skillbag-resource-ingest` is placement/classification only and has no
  bundled helper script for now.
- Added `skillbag-resource-update` for removal, replacement, and supersedence workflows.
- Added source-truth enforcement to `skillbag-resource-sync-index` so orphaned
  derivatives can be reported, hidden from indexes, or pruned deterministically.
- Made resource purpose a required scaffold input and persisted it in
  `resource.yaml`, `metadata.profile.json`, and `README.md`.
- Clarified that ingest/update workflows should run local embeddings by
  default unless the user explicitly disables them.
- Wired published `skillbag-media` into `skillbag-resource-sync-index` so audio/video
  originals can generate local media transcripts under `derivatives/media/`.
