# Project guide

> Audience: Readers who want the whole map before choosing a task.
> Goal: Pick the right page for setup, daily UI use, maintenance, or reference.
> Type: explanation

DJ Track Similarity helps you explore a local music collection when folders, tags, and memory are
not enough. Start from a track you already know, a sound you can describe, or a rough set idea. The
app turns that starting point into a smaller list worth listening to.

It does not decide which tracks are good or guarantee that two tracks will mix. Its job is to reduce
the search space, show why a candidate appeared, and leave the musical decision to you.

The backend and CLI are the active schema-v7 surface. They create a fresh Core plus mandatory
Artifacts bundle, with Evaluation only when needed. They do not migrate older schemas. The React
frontend port is deferred.

## What you can get from it

| Your situation | Start with | Result |
| --- | --- | --- |
| You remember one useful track | MERT or SONARA seed search | A ranked list of nearby candidates to preview |
| You can describe the sound, but not name a track | CLAP text search | A shortlist matched to an audible description |
| You have a few anchors for a set | Smart Set Builder | An editable ordered preview with an energy and tempo direction |
| You want a broad pool for later listening | Filters, seeds, or text search | A crate that you can export as CSV or M3U |
| You repeatedly judge tracks by a personal idea | Rhythm Lab classifier | A reusable per-track score for filtering and gentle SET or Hybrid steering |

Use this guide to choose the shortest route from your current idea to one of those results. Exact
CLI, API, storage, and model contracts remain available in the reference section.

## If you are new

1. Read [Install](./getting-started/install.md).
2. Run [Quickstart](./getting-started/quickstart.md).
3. Build a database with [First library](./getting-started/first-library.md).
4. Add model data with [First analysis](./getting-started/first-analysis.md).
5. Make a first shortlist with [Search with seed tracks](./user-guide/search-with-seeds.md) or [Text search](./user-guide/text-search.md).
6. Preview the results by ear before building a crate or set.

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
- [Prepare and rebuild a SONARA release](./workflows/reanalyze-sonara-split-storage.md) gives the backup, activation, reanalysis, and classifier-rebuild order.
- [Tags and audio writes](./user-guide/tags-and-audio-writes.md) lists the exact file-writing paths.
- [Audio Doctor](./tools-and-scripts/audio-doctor.md) covers dry-run-first repair.
- [Audio Dedup](./tools-and-scripts/audio-dedup.md) covers report-first duplicate checks.
- [Optimize database](./tools-and-scripts/optimize-database.md) covers SQLite maintenance with backup.

## If you need exact contracts

- [CLI reference](./reference/cli.md) lists `dj-sim` commands and standalone tool commands.
- [API reference](./reference/api.md) lists endpoint families and important payloads.
- [Configuration reference](./reference/configuration.md) lists environment variables, ports, local artifacts, and build commands.
- [SONARA v0.2.9 contract](./reference/sonara-v0-2-9-contract.md) defines four output contracts and the Core/Artifacts boundary.
- [UI controls reference](./reference/ui-controls.md) lists ranges and defaults for common controls.
- [Model citations and licenses](./reference/model-citations.md) lists the current upstream model and SONARA sources.

## Current docs build command

Run this from an activated environment with Node dependencies installed:

```powershell
cd docs\dj-track-similarity
npm run check
```

`npm run check` runs strict Vale style checking for `README.md` and the VitePress Markdown tree, then builds the static docs into `site/`.
