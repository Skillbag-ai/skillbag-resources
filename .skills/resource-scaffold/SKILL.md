---
name: resource-scaffold
description: Create, set up, initialize, or validate a portable knowledge base, corpus, reference library, context library, data room, or resource root with persisted purpose, sources, derivatives, metadata, summaries, chunks, and vector indexes. #use/skillbag-python-ensure
dependencies:
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
  - name: resource-purpose
optional:
  - name: resource-name
    default: basename(resource-root)
  - name: resource-root-context-key
    default: RESOURCE_ROOT
  - name: backend
    default: lancedb
  - name: embedding-model
    default: sentence-transformers/all-MiniLM-L6-v2
  - name: overwrite
    default: false
```

## Instructions

- Use this skill when the user asks to create a reusable AI context store,
  including wording such as "create a knowledge base for X in /path", "set up a
  corpus", "initialize a reference library", "make a data room", or "create a
  resource folder".
- Use this skill before any other resource skill writes into a resource
  library.
- Treat `resource-root` as the only portable folder contract exposed to
  dependent skills.
- If `resource-root` is supplied in conversation and is a stable non-secret
  user-local path, persist it to `USER_CONTEXT.md` under
  `resource-root-context-key` unless the user says not to.
- If `resource-root` is missing, ask for the desired local or synced resource
  root path. Do not invent a default path.
- If `resource-purpose` is missing, ask what this resource library is for, who
  will use it, and what kind of material it should contain. Do not scaffold a
  new resource root until this is known.
- Persist the purpose in `resource.yaml`, `metadata.profile.json`, and
  `README.md` so future agents from other projects can continue ingesting with
  the right source structure, metadata, and exclusion decisions.
- Create or validate this structure:

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

- Write `resource.yaml` if missing. It should include:
  - `version`
  - `name`
  - `purpose`
  - `backend`
  - `embedding_model`
  - `created_at`
  - `source_roots`
  - `derivative_roots`
  - `store_root`
- Write `metadata.profile.json` if missing. It should include:
  - resource purpose in metadata defaults
  - workspace metadata defaults when supplied by context
  - path-based metadata rules
  - embedding defaults for post-ingest sync
  - summary defaults
  - chunking defaults
  - embedding model override when different from `resource.yaml`
  - transcript processor preferences that include document, table, and media
    processors when the corresponding public SkillBags are installed
- `store/sqlite/` is the portable fallback database location when LanceDB is
  unavailable.
- Do not define project names, organization names, knowledge categories, or
  organization-specific resource taxonomy.
- If an existing resource root uses another structure, report the mismatch
  unless `overwrite=true`.
- Prefer the bundled helper script for deterministic scaffold creation:

  ```bash
  python3 .skills/resource-scaffold/scripts/resource_scaffold.py \
    --resource-root <resource-root> \
    --purpose "<what this resource library is for>"
  ```

## Outputs

- Resource root directory structure.
- `resource.yaml` configuration.
- `metadata.profile.json` metadata extraction profile when applicable.
- Brief scaffold or validation summary.

## File Boundaries

- May create files and directories under `resource-root`.
- Must not modify source files outside `resource-root`.
