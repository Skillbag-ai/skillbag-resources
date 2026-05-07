---
name: resource-ingest
description: Add, import, collect, or organize files, links, documents, datasets, or messy drops into an existing knowledge base, corpus, reference library, context library, data room, or resource root. #use/resource-scaffold #use/skillbag-python-ensure
dependencies:
  - name: resource-scaffold
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
  - name: source-path
  - name: resource-root
optional:
  - name: ingest-mode
    default: copy
  - name: classification-policy
    default: content-first-path-second
  - name: ambiguity-policy
    default: ask
  - name: destination-profile
    default: scaffold-default
  - name: filename-policy
    default: preserve
```

## Instructions

- Use this skill when the user wants to add material into a reusable AI context
  store, including wording such as "add to the knowledge base", "collect these
  docs", "ingest this data", "organize this data room", or "put this in the
  reference library".
- Use `resource-scaffold` first to validate the resource root.
- Read the resource root `README.md`, `resource.yaml`, and
  `metadata.profile.json` before choosing target paths. The resource purpose is
  part of the ingest contract and should drive source structure, metadata, and
  exclusion decisions.
- Treat clean and messy drops as the same workflow:
  - clean drops can be ingested directly
  - messy drops require classification before placement
- Do not create a competing resource folder structure. Use the scaffold's
  configured paths.
- Recursively inventory `source-path`.
- Classify files by content first, filename second, and folder path third.
- Place confirmed originals under `sources/originals/` unless
  `destination-profile` explicitly says to keep external references.
- Put uncertain files in `staging/quarantine/` when `ambiguity-policy=quarantine`.
  Ask before moving or copying uncertain files when `ambiguity-policy=ask`.
- Do not generate transcripts, structured derivatives, summaries, chunks, or
  embeddings during ingestion. Leave expensive or processor-dependent work to
  `resource-sync-index`.
- If a placed file appears to need downstream processing, record the suggested
  capability in the ingest summary without selecting or running a processor.
- Record an ingest run in `store/state/ingest-runs.jsonl`.
- After apply-mode ingestion, run `resource-sync-index` with embeddings unless
  the user explicitly disables them:

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

- For replacing, superseding, or removing an existing canonical resource, use
  `resource-update` instead of treating the operation as a new messy ingest.

## Outputs

- Ingest summary with placed, skipped, quarantined, and unresolved files.
- Source files or external source records under the scaffold.
- An ingest-run state record.

## File Boundaries

- May read `source-path`.
- May copy or move files into `resource-root` according to `ingest-mode`.
- Must not delete originals unless `ingest-mode=move` and the user explicitly
  supplied that mode.
