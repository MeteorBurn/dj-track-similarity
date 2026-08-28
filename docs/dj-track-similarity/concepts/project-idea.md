# Project idea

`dj-track-similarity` starts from a simple personal problem:

> I have a large folder of music. I want to analyze it locally, rediscover tracks I already own, search by vibe, sound, references, or text, and build DJ sets that mix cleanly and move like a story.

The project is not trying to be a generic recommendation service. It is a local workbench for listening-led set preparation.

## Local library problem

Large local libraries become hard to use when old folder layouts and inconsistent tags hide thousands of files. The right next track may already be there.

The project tries to make that library searchable from several angles:

- file tags and normal library metadata,
- explainable SONARA audio features,
- MAEST, MERT, MuQ, MuQ-MuLan, and CLAP model signals,
- CLAP or MuQ-MuLan text prompts,
- seed-track similarity,
- optional personal classifier scores from Rhythm Lab.

Those signals are not meant to replace listening. They help form a shortlist.

## Set dramaturgy

The north star is local-first DJ set dramaturgy. A set can work like a small narrative that moves from an opening into turns, pressure, release, and a destination.

In that framing, the main question is not only:

> What sounds similar to this track?

It is closer to:

> What track should come next if this set needs to keep flowing while the mood changes slowly?

Similarity is one ingredient. Tempo, key, energy, texture, density, contrast, personal taste, and the intended arc all matter.

## Author stance

This personal enthusiast project comes from an author who does not claim expert knowledge of machine learning, music information retrieval, or every model used by the project.

The project exists first because the author wanted this tool for a personal local library. It may also be useful to other DJs, collectors, and curious listeners who want a practical way to dig through their own music.

That stance shapes the docs and UI:

- model outputs are ranking signals, not objective truth,
- the app should keep evidence sources inspectable and separated,
- automatic previews are starting points for listening,
- the final musical decision belongs to the DJ.

## Current boundary

The boundary between what runs today and what remains direction is worth stating plainly, because
the set-dramaturgy framing above is the goal rather than the feature list.

### Available in the browser

- Library scan, then SONARA analysis in Direct or Staged mode under a library-scoped BPM range.
- MAEST, MERT, MuQ, MuQ-MuLan, and CLAP analysis, in Direct or Staged mode.
- SONARA search across five modes, with mixer weights and nine modifiers.
- Seed search over MAEST, MERT, MuQ, and MuQ-MuLan in the SIMILARITY tab.
- Text search over CLAP or MuQ-MuLan in the PROMPT tab, with a preset picker and relevance verdicts.
- LAB Reference Compare across six model families, with listening verdicts.
- CLASS filters over promoted classifier scores, with per-key reset and rescore.
- A browser-local current set, Rhythm Lab collection transfer, and M3U or CSV export.
- Audio Dedup search, review, and deletion.

### Available from the CLI or the HTTP API only

- CLAP seed search through `POST /api/search`.
- The whole Evaluation package, including candidate pools, score profiles, ablation, and
  calibration. There is no Evaluation UI.
- Library relocation preview and apply.
- Audio Doctor, which has no route in the application at all.
- Audio Online metadata enrichment.
- The benchmark and cross-check scripts behind the text layer.

### Still a direction

Automatic set generation is the largest one. Nothing in the app turns a set of anchors into an
ordered sequence with a chosen energy or tempo direction. The current set is a list you build by
hand, one track at a time, and export in the order you put them.

The narrative arc described above stays a design goal. Similarity, text retrieval, and classifier
scores are the building blocks that exist today.

### Written but waiting for a consumer

Some analysis output is stored and read by nothing yet. The 48-dimensional SONARA embedding is
written on every successful SONARA pass and has no reader in search, classifiers, or Audio Dedup.
The SONARA mood values, true peak, and ReplayGain are stored and available to Rhythm Lab recipes
while staying out of every similarity path. None of this is dead code, and none of it affects a
ranking today.

## Related pages

- [Features, embeddings, and tags](./features-embeddings-tags.md)
- [Similarity scores](./similarity-scores.md)
- [Model citations and licenses](../reference/model-citations.md)
