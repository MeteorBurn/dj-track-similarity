# Choose your first analysis

Audience: new users  
Goal: run the smallest useful analysis pass  
Type: tutorial

Analysis creates local SQLite state that search can use. Pick the analysis
family that matches your immediate goal instead of running everything first.

## Quick choice

| Goal | Start with |
| --- | --- |
| Explainable rhythm, loudness, energy, and texture controls | SONARA |
| Seed-track audio similarity | MERT |
| Text-to-music prompts | CLAP |
| Genre labels and classifier inputs | MAEST |
| Your own labeled concept, after Rhythm Lab promotion | CLASSIFIERS |

## Run a small SONARA pass first

```powershell
dj-sim analyze --models sonara --limit 25 --db .\data\library.sqlite
```

Expected result:

```text
The command reports progress and marks analyzed tracks in the database.
```

In the UI, the summary badges update and the SONARA tab can search from seed
tracks.

## Run heavier model analysis deliberately

MERT, CLAP, and MAEST require the `ml` extra. They can be slow on CPU.

```powershell
dj-sim analyze --models mert --limit 25 --db .\data\library.sqlite
dj-sim analyze --models clap --limit 25 --db .\data\library.sqlite
dj-sim analyze --models maest --limit 25 --db .\data\library.sqlite
```

Use `--device cuda` only when `dj-sim doctor` shows CUDA is available. The
default `--device auto` selects CUDA when PyTorch can see it, otherwise CPU.

## Analyze limit

In the UI, `Analyze limit = 0` means the whole library. A positive limit counts
missing results for the selected analysis family.

## What happens next

- Use [Search with seeds](../user-guide/search-with-seeds.md) after SONARA or
  MERT analysis.
- Use [Text search](../user-guide/text-search.md) after CLAP analysis.
- Use [Smart Set Builder](../user-guide/smart-set-builder.md) after SONARA,
  MERT, MAEST, and CLAP audio embeddings are present.
