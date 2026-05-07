---
name: resource-update
description: Remove, replace, update, supersede, or version canonical originals in a knowledge base, corpus, reference library, context library, data room, or resource root, then refresh derived transcripts, summaries, chunks, and indexes. #use/resource-scaffold #use/resource-ingest #use/resource-sync-index #use/skillbag-python-ensure
dependencies:
  - name: resource-scaffold
    required: true
  - name: resource-ingest
    required: false
  - name: resource-sync-index
    required: true
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
  - name: action
optional:
  - name: target-resource
  - name: replacement-source
  - name: update-policy
    default: replace-or-supersede
  - name: sync-after
    default: true
  - name: orphan-derivative-policy
    default: hide
```

## Instructions

- Use this skill when the user wants to remove stale material or replace it
  with a newer version, including wording such as "replace this regulation in
  the knowledge base", "remove this source", "update this document", or
  "supersede the old dataset".
- Use this skill when the user wants to remove a resource, replace an existing
  resource with a newer file, or add a new version that supersedes an older
  resource such as a regulation, standard, template, or methodology.
- Treat `sources/originals/` as the canonical local source of truth. Do not
  edit generated derivatives directly to perform a replacement.
- Read the resource root `README.md`, `resource.yaml`, and
  `metadata.profile.json` before choosing replacement paths or deciding whether
  an old version should remain searchable.
- Resolve `target-resource` against `sources/originals/` first. If multiple
  candidates match, show the candidates and ask before changing files.
- For a same-document replacement, copy or move `replacement-source` to the
  existing target path under `sources/originals/`. This preserves stable
  resource identity and lets `resource-sync-index --transcript-policy changed`
  refresh stale derivatives.
- For a new named version that should coexist with the old one, ingest or place
  it as a new original under the same collection path. Remove or archive the old
  original only when the user explicitly says the old version is no longer
  authoritative.
- For a hard removal, remove only the canonical original unless the user also
  asks to physically prune generated derivatives.
- After any apply-mode update, run `resource-sync-index` with source-truth
  enforcement:

```bash
python3 .skills/resource-sync-index/scripts/resource_sync_index.py \
  --resource-root <resource-root> \
  --mode apply \
  --chunk-policy changed-only \
  --summary-policy changed \
  --transcript-policy changed \
  --source-truth originals \
  --orphan-derivative-policy hide \
  --embed \
  --write-lancedb \
  --write-sqlite
```

- Use `--orphan-derivative-policy report` for a dry audit, `hide` to remove
  orphaned generated files from state and indexes while leaving files on disk,
  and `prune` only when the user explicitly wants generated derivative files
  physically deleted.

## Outputs

- Update summary describing removed, replaced, superseded, and unchanged
  originals.
- Sync report showing added, changed, removed, orphaned derivatives, summaries,
  chunks, and backend writes.

## File Boundaries

- May read and modify files under `resource-root/sources/originals/`.
- May run `resource-sync-index` to update `resource-root/store/` and generated
  derivatives.
- Must not delete originals, replacements, or generated derivatives without an
  explicit user instruction or an apply-mode command that names the target.
