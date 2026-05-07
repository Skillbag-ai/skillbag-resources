# Security

Resource stores may contain sensitive local files and metadata.

- Do not upload resource contents unless the user explicitly requests it.
- Treat embeddings and transcripts as derived sensitive data.
- Do not persist secrets in `resource.yaml`, state files, or indexes.
- Prefer local models and local file-backed stores for private corpora.

Report security issues through the repository owner.
