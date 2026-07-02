# Find the next track without giving up your library

> Audience: DJs, collectors, and power users opening the docs for the first time.
> Goal: Understand what dj-track-similarity is, why it is useful, and where to go next.
> Type: explanation

`dj-track-similarity` is a local-first music-library helper. It scans tags and stores analysis in SQLite. Use it to find candidates for crates, transitions, text prompts, and set previews. This is a public personal utility for self-managed libraries.

## What it gives you

- A local SQLite view of your library with readable tags and analysis coverage.
- SONARA audio features plus MERT, MAEST, and CLAP embeddings for comparison.
- Seed search, CLAP text search, Smart Set Builder previews, and optional Rhythm Lab classifiers.

## Data flow

```mermaid
flowchart LR
    A[Audio files] --> B[Scan tags]
    B --> C[SQLite library]
    A --> D[Analyze audio]
    D --> C
    C --> E[Search and SET previews]
    E --> F[Manual listening decision]
```

## Safety in one sentence

Most app workflows read audio and write SQLite only. The explicit exceptions are MAEST genre tag apply, Audio Doctor `--apply`, and Audio Dedup apply/delete. Relocation apply updates stored SQLite paths only.

## Start here

- [Getting started](./getting-started/index.md): install, scan, analyze, and see the first useful results.
- [User guide](./user-guide/index.md): daily UI work: browse, search, sets, exports, and safe tag writes.
- [Workflows](./workflows/index.md): DJ-shaped recipes for preparing a set or maintaining a collection.
- [Concepts](./concepts/index.md): plain explanations of features, embeddings, scores, and routing.
- [Tools and scripts](./tools-and-scripts/index.md): covers Rhythm Lab plus maintenance helpers for duplicates, repairs, and database optimization.
- [Reference](./reference/index.md): concise CLI, API, database, config, analysis, and UI facts.
- [Developer](./developer/index.md): architecture, local development, verification, and release checks.
- [Help](./help/index.md): troubleshooting, FAQ, and current limits.
