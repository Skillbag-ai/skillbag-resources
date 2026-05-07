# SkillBag Resources

SkillBag Resources is a companion SkillBag repository for building local,
portable resource libraries that agents can index and query without reading an
entire corpus into the main conversation context.

It provides reusable skills for:

- scaffolding a resource root
- ingesting clean or messy resource drops
- replacing, superseding, or removing canonical originals
- tracking file deltas
- extracting configurable metadata
- generating compact resource summaries for cheap discovery
- chunking text derivatives
- embedding chunks with a local Hugging Face model
- writing a local embedding database
- querying resource records, summaries, and chunks

The core design goal is simple: keep source data and derived indexes local,
deterministic, and reusable across agents.

## SkillBag Source

This repository is itself a valid SkillBag source:

- repository instructions live in [AGENTS.md](./AGENTS.md)
- installed skills live under [`.skills/`](./.skills/)
- the skill catalog lives at [`.skills/SKILLS.md`](./.skills/SKILLS.md)

The repository is intentionally generic. It should not encode one company's
project structure, knowledge categories, naming rules, or archival policy.
Those belong in the consuming workspace as configuration, wrappers, or
migration skills.

## Repository Layout

- [AGENTS.md](./AGENTS.md): repository instructions for agents.
- [README.md](./README.md): package overview and usage notes.
- [CONTRIBUTING.md](./CONTRIBUTING.md): contribution expectations.
- [GOVERNANCE.md](./GOVERNANCE.md): scope and maintenance rules.
- [SUSTAINABILITY.md](./SUSTAINABILITY.md): sustainability policy.
- [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md): community standards.
- [SECURITY.md](./SECURITY.md): security reporting policy.
- [CHANGELOG.md](./CHANGELOG.md): release history.
- [LICENSE.md](./LICENSE.md): license terms.
- [`.skills/SKILLS.md`](./.skills/SKILLS.md): skill catalog.

## Why This Exists

Markdown indexes are useful at small scale, but they become expensive when an
agent has to repeatedly inspect many files to understand what changed or what
is relevant.

SkillBag Resources moves that work into a local resource layer:

1. Keep original files in a predictable resource root.
2. Keep transcripts and structured derivatives beside the originals.
3. Track file identity with size, mtime, and SHA-256.
4. Only process added, changed, or removed files on normal sync runs.
5. Generate compact resource summaries for cheap discovery.
6. Chunk text locally.
7. Embed chunks locally with a Hugging Face SentenceTransformer.
8. Store metadata, summaries, chunks, and vectors in a local file-backed
   database.
9. Let the main agent query the index instead of reading the whole corpus.

This saves tokens and makes repeated work cheaper, faster, and more
reproducible.

## Available Skills

### [resource-scaffold](./.skills/resource-scaffold/SKILL.md)

Creates or validates the portable resource root. Other resource skills should
depend on this instead of creating their own folder structure.

It includes the bundled helper:

[`resource_scaffold.py`](./.skills/resource-scaffold/scripts/resource_scaffold.py)

### [resource-ingest](./.skills/resource-ingest/SKILL.md)

Ingests clean or messy resource drops into an existing scaffold. "Dirty" input
is handled as classification mode, not as a separate folder policy.

### [resource-update](./.skills/resource-update/SKILL.md)

Removes, replaces, or supersedes canonical resource originals, then uses
`resource-sync-index` to refresh generated derivatives, summaries, chunks, and
local indexes.

### [resource-sync-index](./.skills/resource-sync-index/SKILL.md)

Detects added, changed, or removed files and updates local file state,
transcripts, summaries, chunks, embeddings, and the database. It includes the
bundled Python script:

[`resource_sync_index.py`](./.skills/resource-sync-index/scripts/resource_sync_index.py)

### [resource-query](./.skills/resource-query/SKILL.md)

Queries the local store by metadata, summaries, keywords, vector similarity, or
hybrid logic. The query skill is intentionally store-aware but should not
modify the resource root. It includes the bundled helper:

[`resource_query.py`](./.skills/resource-query/scripts/resource_query.py)

Ranked query output is a candidate list, not an oracle. Agents must inspect the
returned snippets or rows and decide which result fits the user question. For
standards, control matrices, and regulations, exact control identifiers, row
titles, source paths, and metadata should override a merely plausible embedding
rank.

## How To Use

Add this repository as a SkillBag dependency in the consuming workspace, usually
alongside:

- `skillbag-utils` for shared runtime helpers such as Python dependency checks.
- `skillbag-docs` for document-to-markdown transcript generation.
- `skillbag-media` when local audio or video processing is needed.

Example dependency note for a consuming workspace:

```markdown
## SkillBag Dependencies

- git@github.com:Skillbag-ai/skillbag-utils.git
- git@github.com:Skillbag-ai/skillbag-docs.git
- git@github.com:Skillbag-ai/skillbag-resources.git
```

Typical workflow:

1. Use `resource-scaffold` to create a resource root and persist its purpose.
2. Use `resource-ingest` to place clean or messy drops under
   `sources/originals/` or `sources/external/`.
3. Use `resource-sync-index` in plan mode to review changes.
4. Use `resource-sync-index` in apply mode to generate transcripts, summaries,
   chunks, embeddings, and local indexes.
5. Use `resource-query` to retrieve ranked candidates, then inspect the
   returned snippets, rows, source paths, and metadata before answering.

Common activation wording should map to this skill set. Examples:

- "create a knowledge base for X in `/path`"
- "set up a corpus/reference library/context library"
- "collect these documents for later AI work"
- "ingest this data room"
- "sync/index/rebuild the knowledge base"
- "find what we know about X in the resource library"

For a first full build:

```bash
python3 .skills/resource-sync-index/scripts/resource_sync_index.py \
  --resource-root /path/to/resources \
  --mode apply \
  --chunk-policy all \
  --summary-policy missing \
  --transcript-policy missing \
  --embed \
  --write-lancedb \
  --write-sqlite
```

For normal incremental syncs:

```bash
python3 .skills/resource-sync-index/scripts/resource_sync_index.py \
  --resource-root /path/to/resources \
  --mode apply \
  --chunk-policy changed-only \
  --summary-policy changed \
  --transcript-policy changed \
  --embed \
  --write-lancedb \
  --write-sqlite
```

## Resource Root Layout

`resource-scaffold` owns this layout:

```text
resources/
  resource.yaml
  README.md
  metadata.profile.json
  sources/
    originals/
    external/
  derivatives/
    transcripts/
    structured/
    media/
    normalized/
  store/
    lancedb/
    sqlite/
      resources.db
    state/
      file-state.jsonl
      ingest-runs.jsonl
      sync-runs.jsonl
      summaries.jsonl
      chunks.jsonl
    exports/
  staging/
    incoming/
    quarantine/
```

### Main Files

- `resource.yaml`: resource-root name, purpose, backend preference, embedding
  model, source roots, derivative roots, and state paths.
- `metadata.profile.json`: workspace metadata defaults and path rules,
  including the persisted resource purpose. This is where project-specific
  metadata extraction belongs.
- `README.md`: local notes for the resource root. It must explain what the
  resource library is for so future agents can keep ingest decisions coherent.

### Source And Derivative Areas

- `sources/originals/`: canonical copied or moved source files. This is the
  normal local source of truth.
- `sources/external/`: optional manifests or pointers for files that remain
  outside the resource root. Use this for URL, API, SaaS, cloud storage, or
  shared-drive pointers where the resource library should know about the source
  but should not own a local copy.
- `derivatives/transcripts/`: text transcripts derived from documents, audio,
  video, or other source files.
- `derivatives/structured/`: table extraction, CSV, JSON, spreadsheet, or
  structured parse outputs.
- `derivatives/media/`: media-specific derivatives, such as video scene notes
  or speech transcripts.
- `derivatives/normalized/`: normalized text or other canonical downstream
  representations.

### Store Area

- `store/state/file-state.jsonl`: latest file inventory with hashes and
  metadata.
- `store/state/ingest-runs.jsonl`: append-only ingest events.
- `store/state/sync-runs.jsonl`: append-only sync/index events.
- `store/state/summaries.jsonl`: compact resource-level summaries and keywords
  for cheap discovery before reading full chunks.
- `store/state/chunks.jsonl`: chunk records; may include vectors when
  embedding is enabled.
- `store/lancedb/`: preferred vector database location when LanceDB is
  installed and working.
- `store/sqlite/resources.db`: fallback local database with resources, chunks,
  metadata, and vectors.
- `store/exports/`: imported legacy indexes or portable export files.

### Staging Area

- `staging/incoming/`: optional landing area for raw drops.
- `staging/quarantine/`: uncertain files awaiting classification.

## Data Flow

The normal lifecycle is:

```text
incoming files
  -> resource-ingest
  -> sources/originals or sources/external
  -> resource-sync-index plan
  -> resource-sync-index apply
  -> transcript or structured derivative generation
  -> file-state, summaries, chunks, embeddings, database
  -> resource-query
```

Ingestion and indexing are deliberately separate:

- ingestion places files and records what happened
- indexing discovers processors, decides what changed, generates missing/stale
  transcripts when configured, and refreshes metadata, summaries, chunks, and
  embeddings

This separation prevents a messy file drop from forcing an expensive embedding
or summary run before the placement and metadata are right.

For replacements and removals, the lifecycle is:

```text
replacement or removal request
  -> resource-update
  -> sources/originals changed as the canonical truth
  -> resource-sync-index apply
  -> stale derivatives hidden or pruned according to policy
  -> summaries, chunks, embeddings, and database refreshed
```

## Processor Discovery

Resource management should be flexible about how files become agent-readable.
`skillbag-docs` is the default document-processing dependency, but it should
not be the only possible path.

The expected discovery order is:

1. current workspace `.skills/SKILLS.md`
2. repository-local skill indexes such as `skills/README.md`
3. declared dependency catalogs, such as `skillbag-docs`
4. fallback built-in scripts, when available

The sync/index skill should classify processors by capability:

- document transcript generation
- PDF OCR
- table or spreadsheet extraction
- image OCR
- audio/video transcription
- archive unpacking
- code or infrastructure analysis
- custom structured extraction

Then it should select the best processor for the file type and project scope.
For example, a future `skillbag-media` transcript skill should be preferred for
video files when it is installed and the resource profile says media processing
is in scope. The document transcript fallback should still handle PDFs, Word
documents, ODT files, images, and plain text when no more specific processor is
available.

The sync script supports deterministic processor override through
`metadata.profile.json`. By default, it can call the sibling `skillbag-docs`
`document-to-markdown-transcript` helper when the hub repos are checked out
beside each other:

```json
{
  "transcripts": {
    "processor_command": [
      "python3",
      "/path/to/current-project/.skills/special-transcriber/scripts/transcribe.py",
      "{input}",
      "{output}",
      "--language",
      "{language}"
    ]
  }
}
```

Supported placeholders are `{input}`, `{output}`, and `{language}`.

## Delta Detection

The bundled sync script scans configured roots and compares the current files
against `store/state/file-state.jsonl`.

For each file it records:

- resource-root-relative path
- kind, such as source, transcript, structured, normalized, or metadata export
- size
- mtime in nanoseconds
- SHA-256 hash
- status, such as present or removed
- extracted metadata

The delta result has four buckets:

- `added`: no prior state record exists
- `changed`: path exists but hash or size changed
- `removed`: prior state exists but the file is gone
- `unchanged`: current state matches prior state

Normal sync runs should use changed-only chunking:

```bash
python3 .skills/resource-sync-index/scripts/resource_sync_index.py \
  --resource-root /path/to/resources \
  --mode apply \
  --chunk-policy changed-only
```

Cheap local query against the portable state files:

```bash
python3 .skills/resource-query/scripts/resource_query.py \
  --resource-root /path/to/resources \
  --query "key rotation" \
  --mode hybrid \
  --top-k 10
```

Use full chunking only for the first build or an intentional rebuild:

```bash
python3 .skills/resource-sync-index/scripts/resource_sync_index.py \
  --resource-root /path/to/resources \
  --mode apply \
  --chunk-policy all
```

## Metadata Profiles

Metadata extraction is configurable. The portable skills should not know a
workspace taxonomy, sensitivity labels, project names, or collection logic.

Put those rules in `metadata.profile.json` or pass another profile through the
`--metadata-profile` option.

Example:

```json
{
  "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
  "defaults": {
    "resource_purpose": "Reusable knowledge base for project or team reference material",
    "workspace": "example-workspace",
    "domain": "knowledge-management",
    "sensitivity": "internal"
  },
  "embeddings": {
    "policy": "on-ingest",
    "write_lancedb": true,
    "write_sqlite": true
  },
  "path_rules": [
    {
      "pattern": "sources/originals/reference/standards/**",
      "metadata": {
        "collection": "standards",
        "resource_family": "reference"
      }
    },
    {
      "pattern": "sources/originals/reference/policies/**",
      "metadata": {
        "collection": "policies",
        "resource_family": "reference"
      }
    },
    {
      "pattern": "derivatives/transcripts/reference/**",
      "metadata": {
        "derivative_type": "transcript"
      }
    }
  ],
  "chunking": {
    "max_chars": 1800,
    "overlap_chars": 250
  },
  "summaries": {
    "backend": "huggingface",
    "model": "sshleifer/distilbart-cnn-12-6",
    "max_chars": 900,
    "max_input_chars": 6000,
    "hf_min_length": 40,
    "hf_max_length": 180,
    "keyword_limit": 16
  },
  "sync": {
    "source_truth": "originals",
    "orphan_derivative_policy": "hide"
  },
  "transcripts": {
    "language": "eng",
    "policy": "missing",
    "processor_preference": [
      "current-project-special-transcriber",
      "document-to-markdown-transcript",
      "extract-structured-tables",
      "media-transcript"
    ]
  }
}
```

Rules:

- `defaults` apply to every file record unless later rules override them.
- `defaults.resource_purpose` should summarize what the resource root is for.
  Agents must read it before ingesting new files.
- `embeddings.policy=on-ingest` means ingest and update workflows should run
  local embeddings as part of their normal sync.
- `path_rules` use shell-style glob patterns against resource-root-relative
  paths.
- `summaries.backend` controls local summary generation. Use `huggingface` for
  local Hugging Face summaries, `auto` for Hugging Face with extractive
  fallback, or `extractive` for deterministic sentence selection only.
- `summaries.model` defaults to `sshleifer/distilbart-cnn-12-6`.
- `summaries.max_chars`, `max_input_chars`, `hf_min_length`, `hf_max_length`,
  and `keyword_limit` control the cheap resource-level discovery record
  generated by `resource-sync-index`.
- `sync.source_truth` controls the authoritative source area for generated
  derivatives.
- `sync.orphan_derivative_policy` controls whether orphaned generated
  derivatives are reported, hidden from indexes, or physically pruned.
- `category` is inferred automatically for legacy paths that contain
  `knowledge/<category>/`; new resource roots should prefer explicit
  `path_rules`.
- `file_extension` is inferred from the source path.
- workspace-specific fields belong in configuration, not in reusable skill
  text.
- `transcripts.processor_preference` lets a project rank available processors
  without changing reusable skill code.
- `transcripts.processor_command` can pin the exact command for deterministic
  local extraction.

This lets different workspaces use the same sync/index code while extracting
different metadata.

## Transcript Generation

Transcripts are part of the resource management pipeline. A resource root should
not merely reference transcripts and hope they already exist.

By default, `resource-sync-index` runs transcript enforcement before scanning
and chunking:

```bash
python3 .skills/resource-sync-index/scripts/resource_sync_index.py \
  --resource-root /path/to/resources \
  --mode apply \
  --transcript-policy missing
```

Policies:

- `missing`: generate transcripts only where no transcript exists
- `changed`: generate missing transcripts and refresh stale transcripts
- `force`: regenerate all supported transcripts
- `skip`: do not generate transcripts

The bundled script maps originals to transcript targets under
`derivatives/transcripts/`. For legacy folders that used `raw/`, it also checks
for the common collapsed path so existing transcripts are reused instead of
duplicated.

The default fallback processor is the `skillbag-docs`
`document-to-markdown-transcript` script. Projects can override that with a
current-project skill command in `metadata.profile.json`, or with
`--transcript-script` on the command line.

## Resource Summary Generation

Resource summaries belong to `resource-sync-index`, not `resource-ingest`.
Ingest should place files and record what happened; sync/index should create
the cheap discovery layer after source placement, transcript enforcement, and
metadata rules are known.

Summary generation is local. By default it uses a Hugging Face summarization
model, currently `sshleifer/distilbart-cnn-12-6`, and does not call the
ChatGPT/OpenAI API. Set `summaries.backend=extractive` to use deterministic
sentence selection only.

Install local Hugging Face summary dependencies when they are missing:

```bash
python3 -m pip install --user transformers torch
```

By default, `resource-sync-index` writes compact summaries to:

```text
store/state/summaries.jsonl
```

Run normal summary sync with:

```bash
python3 .skills/resource-sync-index/scripts/resource_sync_index.py \
  --resource-root /path/to/resources \
  --mode apply \
  --summary-policy missing
```

Policies:

- `missing`: generate missing or stale summaries
- `changed`: refresh missing or stale summaries
- `force`: regenerate all supported summaries
- `skip`: do not generate summaries when they are not required

Summary records include a title, compact summary text, keywords, metadata, and
the source SHA-256. `resource-query` searches these records before full chunks
so an agent can find likely resources cheaply in a large local corpus.

## Source Truth And Removal Behavior

By default, `sources/originals/` is the authoritative local source tree.
Generated derivatives under `derivatives/` should not keep a resource alive
after its original has been removed.

Run source-truth sync with:

```bash
python3 .skills/resource-sync-index/scripts/resource_sync_index.py \
  --resource-root /path/to/resources \
  --mode apply \
  --chunk-policy changed-only \
  --summary-policy changed \
  --transcript-policy changed \
  --source-truth originals \
  --orphan-derivative-policy hide \
  --write-sqlite
```

Orphan derivative policies:

- `report`: keep orphaned derivatives indexed and report them.
- `hide`: remove orphaned derivatives from file state, summaries, chunks, and
  databases while leaving files on disk.
- `prune`: physically delete orphaned generated derivatives in apply mode.

Use `hide` for normal sync. Use `prune` only when the user explicitly wants
generated derivative files removed from disk.

## Chunking

The sync script chunks text-like files under:

- `derivatives/transcripts/`
- `derivatives/structured/`
- `derivatives/normalized/`
- text-like files under `sources/originals/`
- imported metadata under `store/exports/`

Default chunking:

- `max_chars`: `1800`
- `overlap_chars`: `250`

The chunker tries to split on paragraph boundaries when practical. Chunk
records include:

- chunk ID
- source resource ID
- target path
- chunk index
- character offsets
- chunk text
- metadata
- source SHA-256
- embedding model
- vector, when embedding is enabled

## Embeddings

Embeddings require `sentence-transformers` and a local or downloadable Hugging
Face model. They should run after apply-mode ingest and update workflows unless
the user explicitly disables them.

Install dependencies:

```bash
python3 -m pip install --user sentence-transformers
```

Run the first full embedding build:

```bash
python3 .skills/resource-sync-index/scripts/resource_sync_index.py \
  --resource-root /path/to/resources \
  --mode apply \
  --chunk-policy all \
  --embed \
  --write-lancedb \
  --write-sqlite
```

Run normal changed-only embedding syncs:

```bash
python3 .skills/resource-sync-index/scripts/resource_sync_index.py \
  --resource-root /path/to/resources \
  --mode apply \
  --chunk-policy changed-only \
  --embed \
  --write-lancedb \
  --write-sqlite
```

The default model is:

```text
sentence-transformers/all-MiniLM-L6-v2
```

You can override it in `resource.yaml`, `metadata.profile.json`, or the command
line:

```bash
python3 .skills/resource-sync-index/scripts/resource_sync_index.py \
  --resource-root /path/to/resources \
  --mode apply \
  --chunk-policy changed-only \
  --embed \
  --model sentence-transformers/all-mpnet-base-v2
```

Important privacy note: embedding runs are local after the model is available.
The first run may download the model from Hugging Face unless it is already in
the local model cache.

## Database Backends

### LanceDB

LanceDB is the preferred first backend because it is local, file-backed,
Python-native, and built for vector search.

Install:

```bash
python3 -m pip install --user lancedb
```

Run with LanceDB output:

```bash
python3 .skills/resource-sync-index/scripts/resource_sync_index.py \
  --resource-root /path/to/resources \
  --mode apply \
  --chunk-policy all \
  --embed \
  --write-lancedb
```

The table is written under:

```text
store/lancedb/
```

### SQLite Fallback

If LanceDB is unavailable or broken in the local Python environment, the script
falls back to SQLite when `--write-lancedb` is requested.

SQLite output:

```text
store/sqlite/resources.db
```

Tables:

- `resources`: one row per resource file
- `chunks`: one row per text chunk, including metadata and vector JSON

You can force SQLite output directly:

```bash
python3 .skills/resource-sync-index/scripts/resource_sync_index.py \
  --resource-root /path/to/resources \
  --mode apply \
  --chunk-policy all \
  --embed \
  --write-sqlite
```

SQLite is not the long-term vector-search target, but it is useful as a
portable local fallback and as a debug format.

## Querying The SQLite Fallback

Basic inspection:

```bash
python3 - <<'PY'
import sqlite3

db = "/path/to/resources/store/sqlite/resources.db"
with sqlite3.connect(db) as conn:
    print(conn.execute("select count(*) from resources").fetchone())
    print(conn.execute("select count(*) from chunks").fetchone())
PY
```

Keyword query:

```bash
python3 - <<'PY'
import sqlite3

db = "/path/to/resources/store/sqlite/resources.db"
term = "%threshold signing%"
with sqlite3.connect(db) as conn:
    rows = conn.execute(
        "select target_path, chunk_index, substr(text, 1, 300) "
        "from chunks where text like ? limit 10",
        (term,),
    ).fetchall()
    for row in rows:
        print(row)
PY
```

Vector query support lives in `resource-query`. LanceDB is the preferred
backend; the SQLite fallback and `chunks.jsonl` store vectors as JSON so local
cosine search remains possible without a server backend.

## Migration Guidance

Legacy migration is intentionally not included as a portable SkillBag Resources
skill.

Why:

- legacy folders usually encode workspace-specific assumptions
- category names may be local metadata, not portable structure
- old markdown indexes may contain organization-specific fields
- migration often needs one-time judgment

The recommended pattern is:

1. Keep migration in the consuming workspace.
2. Copy original files into `sources/originals/`.
3. Copy transcripts into `derivatives/transcripts/`.
4. Preserve old indexes under `store/exports/`.
5. Store legacy categories as metadata, not as a reusable skillbag rule.
6. Run `resource-sync-index` after migration.

## Security And Privacy

Treat resource roots as sensitive by default.

- Original files may contain confidential source material.
- Transcripts may expose text that was hidden inside binary documents.
- Embeddings can leak semantic information even when raw text is not present.
- Local databases should be protected like the original corpus.
- Do not upload resource content or embeddings unless the user explicitly asks.
- Do not persist secrets in `resource.yaml`, `metadata.profile.json`, or state
  files.

## Development Notes

SkillBag Resources should stay small and composable:

- resource-root structure belongs in `resource-scaffold`
- ingestion placement and classification belong in `resource-ingest`
- transcript enforcement, resource summaries, delta tracking, chunking, and
  embeddings belong in `resource-sync-index`
- querying belongs in `resource-query`
- document parsing belongs in `skillbag-docs`
- legacy migration belongs in consuming workspaces

When adding scripts:

- keep them deterministic and local-first
- make expensive processing incremental
- expose configuration through files or CLI parameters
- avoid requiring the main agent to read the whole corpus
- write clear state records for auditability
- do not add a `resource-ingest` helper script until ingestion needs
  deterministic automation beyond the skill instructions

## Roadmap

Planned or likely next steps:

- media transcript support through a media skillbag
- configurable document extraction profiles
- metadata schema validation
- vector-store backend adapters
- query ergonomics for mixed metadata, keyword, vector, and full-text search
- export/import utilities
- deletion and tombstone compaction tools
- optional full-text search indexes

## Contributing

Contributions should keep this repository portable across teams and projects.
Reusable mechanics belong in skills and scripts; local taxonomies, collection
names, and migration judgments belong in consuming workspaces.

Before proposing changes, keep [`.skills/SKILLS.md`](./.skills/SKILLS.md)
synchronized with skill directories and run relevant script checks such as
`python3 -m py_compile` and `git diff --check`.

See [CONTRIBUTING.md](./CONTRIBUTING.md) for contribution expectations.

## Security

Resource roots often hold confidential material even when this repository is
public. Do not add real corpus content, embeddings, private metadata, or
workspace-specific secrets to this repository.

For vulnerability reporting, see [SECURITY.md](./SECURITY.md).

## License

Released under the MIT license. See [LICENSE.md](./LICENSE.md).
