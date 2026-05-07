# SkillBag Resources

SkillBag Resources is a companion SkillBag repository for creating and using
local knowledge bases in AI-assisted work.

Use it when a workspace needs a reusable place for material that agents can
collect, organize, index, and search later: documents, standards,
policies, notes, research packets, datasets, source references, or external
links.

It is meant for prompts like:

- "create a knowledge base for this project in `/path/to/resources`"
- "collect these documents for later AI work"
- "ingest this data room"
- "sync and index the resource library"
- "find what we know about key rotation in the corpus"
- "replace this old regulation with the new version"

The skills keep original files local, create lightweight discovery records,
and maintain searchable indexes so agents do not need to repeatedly read an
entire corpus into the conversation.

This repository is itself a valid SkillBag source:

- repository instructions live in [AGENTS.md](./AGENTS.md)
- installed skills live under [`.skills/`](./.skills/)
- the skill catalog lives at [`.skills/SKILLS.md`](./.skills/SKILLS.md)

The skills here are meant to be installed into other workspaces as
dependencies. They are kept generic and independent of one organization's
folder naming, taxonomy, or retention policy.

## Available Skills

### [resource-scaffold](./.skills/resource-scaffold/SKILL.md)

Creates or validates a portable resource root. The scaffold records what the
knowledge base is for, where originals live, where generated derivatives live,
and which local indexing backend to use.

Use this when creating a new knowledge base, corpus, reference library,
context library, data room, or resource folder.

Key parameters:

- `resource-root` is required
- `resource-purpose` is required
- `resource-name` defaults to the folder name
- `backend` defaults to `lancedb`
- `embedding-model` defaults to `sentence-transformers/all-MiniLM-L6-v2`

### [resource-ingest](./.skills/resource-ingest/SKILL.md)

Adds material to an existing resource root. It handles both clean inputs and
messy drops by classifying files before placing them in the knowledge base.

Use this when adding documents, folders, datasets, links, or collected research
for future AI work.

Key parameters:

- `source-path` is required
- `resource-root` is required
- `ingest-mode` defaults to `copy`
- `classification-policy` defaults to `content-first-path-second`
- `ambiguity-policy` defaults to `ask`

Behavior:

- reads the resource purpose before deciding where material belongs
- keeps canonical originals separate from generated derivatives
- records ingest events for later audit
- leaves transcript generation, summaries, chunks, and embeddings to
  `resource-sync-index`

### [resource-sync-index](./.skills/resource-sync-index/SKILL.md)

Refreshes the resource store after files are added, changed, removed, or
replaced. It creates the cheap discovery layer: transcripts where available,
resource summaries, chunks, embeddings, and local indexes.

Use this when a knowledge base needs to become searchable or be brought up to
date.

Key parameters:

- `resource-root` is required
- `transcript-policy` defaults to `missing`
- `summary-policy` defaults to `missing`
- `chunk-policy` defaults to `changed-only`
- `source-truth` defaults to `originals`
- `orphan-derivative-policy` defaults to `hide`

Behavior:

- detects added, changed, removed, and unchanged files
- updates only changed material during normal syncs
- can use `skillbag-docs` for document-to-markdown transcripts
- creates compact summaries before full chunk search
- uses local Hugging Face models for embeddings and summaries when configured
- keeps generated derivatives from outliving removed originals unless the
  workspace explicitly wants that

### [resource-query](./.skills/resource-query/SKILL.md)

Searches a local resource store by metadata, summaries, keywords, vector
similarity, or hybrid ranking.

Use this when asking what the knowledge base already contains or when looking
for supporting context before doing AI work.

Key parameters:

- `resource-root` is required
- `query` is required
- `mode` defaults to `hybrid`
- `top-k` defaults to `10`
- `include-source-links` defaults to `true`

Behavior:

- returns ranked candidates with source-aware evidence
- searches summaries before falling back to deeper chunks
- supports exact identifiers and row-level evidence for structured references
- treats vector ranking as a candidate signal, not final truth

### [resource-update](./.skills/resource-update/SKILL.md)

Removes, replaces, updates, or supersedes canonical originals in a resource
root, then refreshes the derived transcripts, summaries, chunks, embeddings,
and indexes.

Use this when a knowledge base needs to remove stale material or replace an old
source with a new version.

Key parameters:

- `resource-root` is required
- `action` is required
- `target-resource` identifies the existing source when needed
- `replacement-source` supplies the new file when replacing or superseding
- `sync-after` defaults to `true`

Behavior:

- treats `sources/originals/` as the local source of truth
- preserves stable paths for same-document replacements
- supports superseding old versions without deleting them when that is useful
- hides or prunes stale generated derivatives according to policy

## How It Works

SkillBag Resources uses a simple local structure:

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
    state/
    lancedb/
    sqlite/
  staging/
```

The important idea is separation:

- `sources/originals/` holds canonical files copied or moved into the resource
  root.
- `sources/external/` holds pointers to material that stays outside the
  resource root.
- `derivatives/` holds generated transcripts, structured outputs, and
  normalized text.
- `store/` holds state, summaries, chunks, embeddings, and local indexes.
- `staging/` gives agents a safe place for uncertain incoming material.

This structure makes the knowledge base portable and predictable. A different
workspace can use the same skills while defining its own metadata rules,
categories, sensitivity labels, and storage policy.

## How To Use

Typical usage is to add this repository as a SkillBag dependency from another
workspace, usually alongside:

- [`skillbag-utils`](https://github.com/Skillbag-ai/skillbag-utils) for shared
  runtime helpers
- [`skillbag-docs`](https://github.com/Skillbag-ai/skillbag-docs) for document
  transcripts, OCR, table extraction, diagrams, and Word document generation
- `skillbag-media` for local audio and video processing when that repository
  is available

Once installed, users can ask in natural language. For example, an agent with
these skills available can understand that "create a knowledge
base", "set up a corpus", "ingest these resources", "sync the data room", and
"search the reference library" all map to this resource skill set.

## Design Notes

SkillBag Resources is local-first. Source files, transcripts, summaries,
chunks, embeddings, and databases stay on the user's machine unless another
workspace explicitly adds a remote storage policy.

The skills are intentionally generic. They provide reusable mechanics:
scaffolding, ingest, sync, summaries, embeddings, query, replacement, and
removal. Project-specific taxonomies and migration decisions belong in the
consuming workspace.

Query results are evidence candidates. Good answers come from inspecting the
returned snippets, rows, paths, and metadata, especially for standards,
regulations, control matrices, or any source where exact identifiers matter.

## Repository Layout

- [AGENTS.md](./AGENTS.md): repository-level installation metadata
- [README.md](./README.md): project overview
- [CONTRIBUTING.md](./CONTRIBUTING.md): contribution guidance
- [GOVERNANCE.md](./GOVERNANCE.md): resource-skill repository governance
- [SUSTAINABILITY.md](./SUSTAINABILITY.md): funding and maintenance model
- [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md): collaboration standards
- [SECURITY.md](./SECURITY.md): security reporting guidance
- [CHANGELOG.md](./CHANGELOG.md): notable repository changes
- [LICENSE.md](./LICENSE.md): MIT license
- [`.skills/SKILLS.md`](./.skills/SKILLS.md): low-cost skill discovery catalog

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## Security

See [SECURITY.md](./SECURITY.md).

## License

Released under the MIT license. See [LICENSE.md](./LICENSE.md).
