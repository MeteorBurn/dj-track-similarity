# Project guide

> Audience: Readers who want the whole map before choosing a task.
> Goal: Pick the right page for setup, daily UI use, maintenance, or reference.
> Type: explanation

Use this guide as the table of contents for real work. The docs describe the current code surface: `dj-sim`, the FastAPI routes under `/api`, the React UI, and the helper tools under `tools/` and `scripts/`.

## If you are new

1. Read [Install](./getting-started/install.md).
2. Run [Quickstart](./getting-started/quickstart.md).
3. Build a database with [First library](./getting-started/first-library.md).
4. Add model data with [First analysis](./getting-started/first-analysis.md).
5. Learn the UI through [Browse library](./user-guide/browse-library.md) and [Search with seed tracks](./user-guide/search-with-seeds.md).

## If you want to prepare music

- Use [Prepare a set](./workflows/prepare-a-set.md) for the full seed-to-export flow.
- Use [Find compatible tracks](./workflows/find-compatible-tracks.md) when you have one or more reference tracks.
- Use [Build crates](./workflows/build-crates.md) when you want a listening pool rather than a final order.
- Use [Smart Set Builder](./user-guide/smart-set-builder.md) for SET controls and Hybrid preview.
- Use [Text search](./user-guide/text-search.md) when you know the sound but not the seed.

## If you want to understand the signals

- [Project idea](./concepts/project-idea.md) explains the local-first DJ set dramaturgy goal and the author's modest scope.
- [Features, embeddings, and tags](./concepts/features-embeddings-tags.md) explains what each stored signal means.
- [Similarity scores](./concepts/similarity-scores.md) explains why MERT, SONARA, CLAP, SET, Hybrid, and Audio Dedup scores should not be mixed casually.
- [SET routing](./concepts/smart-set-builder-routing.md) explains why the generated order is a preview, not a guarantee.
- [Classifiers and Rhythm Lab](./concepts/classifiers-and-rhythm-lab.md) explains local classifier profiles and promoted scores.

## If you are maintaining a library

- [Maintain library](./workflows/maintain-library.md) gives a safe routine.
- [Tags and audio writes](./user-guide/tags-and-audio-writes.md) lists the exact file-writing paths.
- [Audio Doctor](./tools-and-scripts/audio-doctor.md) covers dry-run-first repair.
- [Audio Dedup](./tools-and-scripts/audio-dedup.md) covers report-first duplicate checks.
- [Optimize database](./tools-and-scripts/optimize-database.md) covers SQLite maintenance with backup.

## If you need exact contracts

- [CLI reference](./reference/cli.md) lists `dj-sim` commands and standalone tool commands.
- [API reference](./reference/api.md) lists endpoint families and important payloads.
- [Configuration reference](./reference/configuration.md) lists environment variables, ports, local artifacts, and build commands.
- [UI controls reference](./reference/ui-controls.md) lists ranges and defaults for common controls.
- [Model citations and licenses](./reference/model-citations.md) lists the current upstream model and SONARA sources.

## Current docs build command

Run this from an activated environment with Node dependencies installed:

```powershell
cd docs\dj-track-similarity
npm run check
```

`npm run check` runs strict Vale style checking for `README.md` and the VitePress Markdown tree, then builds the static docs into `site/`.
