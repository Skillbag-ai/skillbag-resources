---
name: resource-query
description: Find, search, retrieve, or answer from a local knowledge base, corpus, reference library, context library, data room, resource store, or indexed collection using metadata, summaries, keywords, or vector similarity. #use/resource-scaffold #use/skillbag-python-ensure
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
  - name: resource-root
  - name: query
optional:
  - name: mode
    default: hybrid
  - name: top-k
    default: 10
  - name: filters
  - name: include-source-links
    default: true
```

## Instructions

- Use this skill when the user wants to find or answer from previously
  collected material, including wording such as "search the knowledge base",
  "what do we know about", "find in the corpus", "retrieve from resources", or
  "use the indexed reference library".
- Use `resource-scaffold` first to validate the resource root.
- Load the configured local backend from `resource.yaml`.
- For cheap local search over the portable state files, prefer the bundled
  helper:

  ```bash
  python3 .skills/resource-query/scripts/resource_query.py --resource-root <resource-root> --query "<query>" --mode hybrid --top-k 10
  ```

- Support these query modes:
  - `metadata`: filter resource records only
  - `keyword`: search text/chunk fields
  - `vector`: embed the query locally and search vector chunks
  - `hybrid`: combine metadata/keyword/vector signals
- Treat ranked results as candidates, not final truth. Retrieve enough results
  for the question, inspect the actual source snippets or rows, and choose the
  answer using source context, exact identifiers, metadata, and user intent.
  This is mandatory for standards and control matrices where a literal control
  ID or control title can be more reliable than embedding similarity.
- The bundled helper supports metadata, summary, keyword, and hybrid search
  over `store/state/file-state.jsonl`, `store/state/summaries.jsonl`, and
  `store/state/chunks.jsonl`. Vector search requires the configured vector
  backend or JSONL vectors to be available.
- Vector mode uses the configured local Hugging Face SentenceTransformer model,
  normally `sentence-transformers/all-MiniLM-L6-v2`. It must not call the
  ChatGPT/OpenAI API. The first run may download the model from Hugging Face if
  it is not already cached locally.
- Return source-aware results:
  - title or filename
  - source path or external pointer
  - resource summary when the match comes from `summaries.jsonl`
  - derivative path when the match comes from a transcript
  - chunk excerpt
  - metadata
  - score when available
- Do not modify the store during query.

## Outputs

- Ranked result list with source-aware citations.
- Brief note if the index is stale or missing.

## File Boundaries

- May read `resource-root`.
- Must not create, update, or delete files.
