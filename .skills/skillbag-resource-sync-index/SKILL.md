---
name: skillbag-resource-sync-index
description: Sync, index, refresh, rebuild, transcribe, summarize, chunk, or embed added, changed, or removed files in a knowledge base, corpus, reference library, context library, data room, or resource root. #use/skillbag-resource-scaffold #use/document-to-markdown-transcript #use/media-transcript #use/skillbag-python-ensure
dependencies:
  - name: skillbag-resource-scaffold
    required: true
  - name: document-to-markdown-transcript
    source: git@github.com:Skillbag-ai/skillbag-docs.git
    version: main
    required: false
  - name: extract-structured-tables
    source: git@github.com:Skillbag-ai/skillbag-docs.git
    version: main
    required: false
  - name: media-transcript
    source: git@github.com:Skillbag-ai/skillbag-media.git
    version: main
    required: false
  - name: skillbag-python-ensure
    source: git@github.com:Skillbag-ai/skillbag-utils.git
    version: main
    required: true
allowed-tools: python3 python
metadata:
  author: backupdev
  version: 0.3.0
---

## Parameters

```yaml
required:
  - name: resource-root
optional:
  - name: backend
    default: from-resource-yaml
  - name: embedding-model
    default: from-resource-yaml
  - name: change-detection
    default: size-mtime-hash
  - name: transcript-policy
    default: missing
  - name: chunk-policy
    default: changed-only
  - name: summary-policy
    default: missing
  - name: dry-run
    default: false
  - name: metadata-profile
    default: metadata.profile.json
  - name: embed
    default: false
  - name: write-lancedb
    default: false
  - name: write-sqlite
    default: false
  - name: rebuild-caches
    default: false
  - name: transcript-script
    default: auto
  - name: source-truth
    default: originals
  - name: orphan-derivative-policy
    default: hide
```

## Instructions

- Use this skill when the user wants the reusable AI context store to become
  searchable, cheap to inspect, or up to date, including wording such as "sync
  the knowledge base", "index this corpus", "rebuild embeddings", "generate
  summaries", or "make this data searchable".
- Use `skillbag-resource-scaffold` first to validate the resource root.
- Prefer the bundled delta/index script instead of having the main agent read
  the corpus:
  `python3 .skills/skillbag-resource-sync-index/scripts/resource_sync_index.py --resource-root <resource-root> --mode plan`
- Use `--mode apply` to update `store/state/file-state.jsonl` and, when text
  chunks are selected, the chunk shards under `store/state/chunks/`.
- `store/state/` is the canonical index; commit it when the workspace versions
  its resource root. Chunks and embeddings live in one small JSONL shard per
  indexed file (`store/state/chunks/<target-path>.jsonl`, vectors as base64
  float16). A sync rewrites only the shards of changed files, deletes shards of
  removed files, keeps stored embeddings when a run does not embed, and repairs
  shards that are missing or no longer match their file even when file state
  says nothing changed (files without text need no shard). A legacy `store/state/chunks.jsonl` is migrated to shards on the
  next apply or `--rebuild-caches`, keeping its embeddings; existing shards
  take precedence.
- When migrating a resource root whose caches were committed, also run
  `git rm -r --cached store/lancedb store/sqlite` in it; migration adds the
  `.gitignore` entries.
- Use `--transcript-policy missing` to generate missing transcripts before
  scanning and chunking. Use `changed`, `force`, or `skip` when needed.
- Use `--summary-policy missing` to generate or refresh cheap resource-level
  summaries for text-like records before query. Summaries use the configured
  local Hugging Face summarization model by default, not the ChatGPT/OpenAI
  API. Use `changed`, `force`, or `skip` when summaries are stale,
  intentionally rebuilt, or not required.
- When `summaries.backend=huggingface`, ensure `transformers` and `torch` are
  available in the selected Python environment.
- Use `--source-truth originals` to treat `sources/originals/` as the
  authoritative local source tree for generated derivatives.
- Use `--orphan-derivative-policy hide` during normal sync so transcripts,
  structured outputs, and normalized files without a corresponding original are
  removed from state, summaries, chunks, and SQLite/LanceDB outputs without
  deleting the files from disk. Use `report` for audits and `prune` only when
  the user explicitly wants orphaned generated derivatives physically deleted.
- The bundled script auto-discovers sibling transcript helpers by file type:
  `skillbag-docs` `document-to-markdown-transcript` for documents/images and
  `skillbag-media` `media-transcript` for audio/video. Pass
  `--transcript-script` or configure `metadata.profile.json` to override this
  with a better current-project processor.
- Use `--chunk-policy all` for the first local chunk build, then
  `--chunk-policy changed-only` for normal delta runs.
- Use `--embed` to pipe changed text chunks through the configured local
  Hugging Face SentenceTransformer. Embedding runs must not call the
  ChatGPT/OpenAI API.
- Post-ingest and post-update syncs should normally include `--embed`,
  `--write-lancedb`, and `--write-sqlite` so the resource library is
  immediately searchable by vector, summary, and local database lookup. Skip
  embeddings only when the user explicitly asks to avoid the cost.
- Use `--write-lancedb` with `--embed` when `lancedb` is installed and the
  vector table should be refreshed under `store/lancedb/`. If LanceDB is
  unavailable, the bundled script writes a SQLite fallback database under
  `store/sqlite/resources.db`.
- Use `--write-sqlite` to write the compact SQLite fallback database directly.
  SQLite keeps resource, summary, chunk text, metadata and embedding-model
  fields but no vector payloads; vectors live in the chunk shards and LanceDB.
- `store/lancedb/` and `store/sqlite/` are local caches built from the shards
  without re-embedding; keep them out of Git. After a clone or pull, run
  `--rebuild-caches` (no scan, no embedding) or let `skillbag-resource-query`
  search the shard vectors in memory until the cache is rebuilt. Caches record
  a content hash of the shard files, so a pull, merge or checkout that changes
  shards marks them stale.
- Load workspace metadata rules from `metadata.profile.json` by default.
  See [`references/metadata-profile.md`](references/metadata-profile.md).
- Read the resource purpose from `resource.yaml`, `metadata.profile.json`, or
  `README.md` before interpreting path rules or deciding whether material
  belongs in this library.
- Load `resource.yaml` and the previous `store/state/file-state.jsonl`
  records.
- Scan configured source and derivative roots.
- Enforce source truth before diffing state. Generated derivatives are valid
  only when the corresponding local source still exists under the configured
  source-truth root.
- Detect file status using stable path, size, mtime, and content hash:
  - added
  - changed
  - removed
  - unchanged
- Before chunking, ensure usable text derivatives exist when possible.
  Delegate extraction to the best matching processor from the current project
  skill set, then to dependency skills such as `skillbag-docs` and
  `skillbag-media`, instead of duplicating parsers.
- Generate compact local Hugging Face summaries for text-like source and
  derivative records so future agents can search `store/state/summaries.jsonl`
  cheaply before reading full chunks from a large corpus. If
  `summaries.backend=extractive`, use deterministic sentence selection instead.
- Chunk only changed text derivatives unless `chunk-policy` requests a broader
  rebuild.
- Embed changed chunks with the configured Hugging Face model when `embed=true`.
- Update the local backend:
  - source/file records
  - derivative records
  - chunk records
  - embedding vectors
  - removal/tombstone records for deleted files
- Preferred backend: local LanceDB under `store/lancedb/`, rebuilt as a cache
  from the committed shards.
- Keep sync idempotent. Re-running without file changes should report no
  material updates.

## Proposed Tables

- `resources`: one row per source or external source record.
- `derivatives`: one row per transcript, structured extraction, media
  transcript, or normalized artifact.
- `chunks`: chunk text, source/derivative IDs, offsets, metadata and
  embedding model; vectors stay in the chunk shards and LanceDB.
- `summaries`: one compact discovery row per summarized resource, including
  title, summary text, keywords, source hash, and metadata.
- `events`: sync and ingest events for auditability.

## Outputs

- Sync report with counts by added, changed, removed, unchanged, summarized,
  embedded, and failed.
- Updated local resource backend.
- Updated file-state and sync-run records.

## File Boundaries

- May read files under `resource-root`.
- May create or update files under `resource-root/store/` and
  `resource-root/derivatives/`.
- May remove generated derivative files only when
  `orphan-derivative-policy=prune` is explicitly selected.
- Must not delete originals automatically. Use tombstones for removed files.
