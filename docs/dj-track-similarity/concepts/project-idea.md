# Project idea

> Audience: Readers who want to understand why the project exists.
> Goal: Explain the intent without overstating what the current app can do.
> Type: concept

`dj-track-similarity` starts from a simple personal problem:

> I have a large folder of music. I want to analyze it locally, rediscover tracks I already own, search by vibe, sound, references, or text, and build DJ sets that mix cleanly and move like a story.

The project is not trying to be a generic recommendation service. It is a local workbench for listening-led set preparation.

## Local library problem

Large local libraries become hard to use when old folder layouts and inconsistent tags hide thousands of files. The right next track may already be there.

The project tries to make that library searchable from several angles:

- file tags and normal library metadata,
- explainable SONARA audio features,
- MAEST, MERT, MuQ, and CLAP model signals,
- CLAP text prompts,
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

The current app supports library scanning and analysis, seed and text search, SET and Hybrid previews, local classifier profiles, and playlist export.

It does not yet generate a finished automatic DJ set from a story prompt. That is the direction, not a completed claim.

## Related pages

- [Features, embeddings, and tags](./features-embeddings-tags.md)
- [Similarity scores](./similarity-scores.md)
- [SET routing](./smart-set-builder-routing.md)
- [Model citations and licenses](../reference/model-citations.md)
