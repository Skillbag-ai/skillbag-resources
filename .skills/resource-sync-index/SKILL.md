---
name: resource-sync-index
description: Sync, index, refresh, rebuild, transcribe, summarize, chunk, or embed added, changed, or removed files in a knowledge base, corpus, reference library, context library, data room, or resource root. #use/resource-scaffold #use/document-to-markdown-transcript #use/skillbag-python-ensure
dependencies:
  - name: resource-scaffold
    required: true
  - name: document-to-markdown-transcript
    source: git@github.com:Skillbag-ai/skillbag-docs.git
    version: main
    required: false
  - name: extract-structured-tables
    source: git@github.com:Skillbag-ai/skillbag-docs.git
    version: main
    required: false
  - name: skillbag-python-ensure
    source: git@github.com:Skillbag-ai/skillbag-utils.git
    version: main
    required: true
allowed-tools: python3 python
metadata:
  author: backupdev
  version: 0.1.0
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
- Use `resource-scaffold` first to validate the resource root.
- Prefer the bundled delta/index script instead of having the main agent read
  the corpus:
  `python3 .skills/resource-sync-index/scripts/resource_sync_index.py --resource-root <resource-root> --mode plan`
- Use `--mode apply` to update `store/state/file-state.jsonl` and, when text
  chunks are selected, `store/state/chunks.jsonl`.
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
- The bundled script auto-discovers a sibling `skillbag-docs`
  `document-to-markdown-transcript` helper script as the default fallback.
  Pass `--transcript-script` or configure `metadata.profile.json` to override
  it with a better current-project processor.
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
- Use `--write-sqlite` with `--embed` to write the SQLite fallback database
  directly.
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
  skill set, then to dependency skills such as `skillbag-docs`, instead of
  duplicating parsers.
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
- Preferred backend: local LanceDB under `store/lancedb/`.
- Keep sync idempotent. Re-running without file changes should report no
  material updates.

## Proposed Tables

- `resources`: one row per source or external source record.
- `derivatives`: one row per transcript, structured extraction, media
  transcript, or normalized artifact.
- `chunks`: chunk text, embedding vector, source/derivative IDs, offsets, and
  metadata.
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
