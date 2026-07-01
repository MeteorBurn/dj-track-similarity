# Project guide

> Audience: Readers who want the whole map before choosing a task.
> Goal: Route quickly to tutorials, workflows, explanations, and reference without reading a dump.
> Type: explanation

Use this map to choose the shortest path for your task. Start with the tutorials if you are setting up a new database, use workflows for DJ tasks, and use reference pages when you already know the feature name or command.

## Choose your route

- [Getting started](./getting-started/index.md) — install, scan, analyze, and see the first useful results.
- [User guide](./user-guide/index.md) — daily UI work: browse, search, sets, exports, and safe tag writes.
- [Workflows](./workflows/index.md) — DJ-shaped recipes for preparing a set or maintaining a collection.
- [Concepts](./concepts/index.md) — plain explanations of features, embeddings, scores, and routing.
- [Tools and scripts](./tools-and-scripts/index.md) — Rhythm Lab, duplicate reports, repair helper, and database optimization.
- [Reference](./reference/index.md) — concise CLI, API, database, config, analysis, and UI facts.
- [Developer](./developer/index.md) — architecture, local development, verification, and release checks.
- [Help](./help/index.md) — troubleshooting, FAQ, and current limits.

## Current analysis command

```powershell
dj-sim analyze --models sonara,maest,mert,clap --limit 25 --db .\data\library.sqlite
```

Current options include `--models`, `--device auto|cpu|cuda`, `--top-k`, `--track-batch-size`, `--inference-batch-size`, and `--diagnostics`. Omit `--limit` for the whole library in the CLI. In the UI, `Analyze limit = 0` means whole library because the UI sends no limit.

## Docs build

Source lives in `docs\dj-track-similarity`. Run `npm run build` from that folder for local preview or deployment. Output is `site/`, served by the backend at `/docs/` when present, and ignored by Git.
