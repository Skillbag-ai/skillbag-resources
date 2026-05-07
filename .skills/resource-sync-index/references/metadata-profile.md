# Metadata Profile

`resource-sync-index` can read `metadata.profile.json` from the resource root
or from `--metadata-profile`.

The profile lets a workspace provide metadata extraction rules
without hard-coding them into the portable skill.

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
    "processor_command": [
      "python3",
      "/absolute/path/to/current-project/.skills/special-transcriber/scripts/transcribe.py",
      "{input}",
      "{output}"
    ],
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

- `defaults` apply to every record unless a later rule overrides them.
- `defaults.resource_purpose` should summarize what the resource root is for
  so agents can make consistent ingest and metadata decisions without relying
  on conversation history.
- `embeddings.policy=on-ingest` means ingest/update workflows should run
  `resource-sync-index` with `--embed --write-lancedb --write-sqlite` unless
  the user explicitly disables embeddings.
- `path_rules` use shell-style glob patterns against resource-root-relative
  paths.
- `summaries.backend` controls summary generation. Use `huggingface` for local
  Hugging Face abstractive summaries, `auto` for Hugging Face with extractive
  fallback, or `extractive` for deterministic sentence selection only.
- `summaries.model` is the local Hugging Face summarization model. The default
  is `sshleifer/distilbart-cnn-12-6`.
- `summaries.max_chars`, `max_input_chars`, `hf_min_length`, `hf_max_length`,
  and `keyword_limit` control compact discovery records written to
  `store/state/summaries.jsonl`.
- `sync.source_truth` controls which source area is authoritative for
  generated derivatives. Use `originals` for the normal model where
  `sources/originals/` is the local source of truth, or `all-sources` only when
  external source manifests should also keep derivatives live.
- `sync.orphan_derivative_policy` controls generated derivatives whose source
  no longer exists: `report` keeps them indexed and reports them, `hide`
  removes them from state/indexes while leaving files on disk, and `prune`
  physically deletes them during apply-mode sync.
- `category` is inferred automatically for legacy paths that contain
  `knowledge/<category>/`; new resource roots should prefer explicit
  `path_rules`.
- Workspace-specific fields belong here or in caller context, not in the
  portable skill instructions.
- `transcripts.processor_preference` is advisory. It lets the resource
  pipeline prefer available processors that are in scope for the project, while
  allowing installed processors such as `document-to-markdown-transcript`,
  `extract-structured-tables`, and `media-transcript` to plug in without
  changing the scaffold.
- For high-value screen-share or walkthrough recordings, configure
  `transcripts.processor_command` to call `media-recording-timeline` from
  `skillbag-media` instead of the cheaper default `media-transcript`.
- `transcripts.processor_command` is deterministic. When present, the sync
  script uses it before fallback auto-discovery. Supported placeholders:
  `{input}`, `{output}`, and `{language}`.
