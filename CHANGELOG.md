# Changelog

## 0.3.0

- Store chunks and embeddings as one small JSONL shard per indexed file under
  `store/state/chunks/` (embeddings as base64 float16) instead of a single
  `store/state/chunks.jsonl` that grew with the corpus and was rewritten on
  every sync. Syncs rewrite only changed shards, keep stored embeddings when a
  run does not embed, and repair shards that no longer match their files.
  Existing `chunks.jsonl` files migrate automatically, keeping embeddings.
- Treat LanceDB and SQLite as local caches built from the shards without
  re-embedding. Caches record a content hash computed from the shard files and
  are stale when it differs; `skillbag-resource-sync-index --rebuild-caches`
  recreates them, rebuilds keep no old LanceDB versions, and the SQLite cache
  stores no vectors. `skillbag-resource-query` stays read-only: with a missing
  or stale cache it searches the shard vectors in memory and says so.
- Write file state after chunks and embeddings, so a failed sync is repeated
  instead of silently skipped; keep the committed sync-runs log compact.
- `skillbag-resource-scaffold` and migration add a resource-root `.gitignore`
  for the caches. When migrating a root whose caches were committed, run
  `git rm -r --cached store/lancedb store/sqlite` in it.
- Read JSONL state on newlines only, so text containing U+2028 or U+2029 no
  longer breaks parsing; discover a document transcript helper vendored next
  to the skill.

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
