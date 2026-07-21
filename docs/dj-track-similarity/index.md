<div class="dts-hero">
  <div class="dts-hero-copy">
    <p class="dts-kicker">Rediscover music on your machine</p>
    <h1>Find the next track without giving up your library</h1>
    <p class="dts-hero-lead">
      Turn a large local collection into a searchable library. Start from a track or a written
      idea, then shape useful candidates into crates and set previews.
    </p>
    <div class="dts-hero-actions">
      <a class="dts-button dts-button-brand" href="./getting-started/quickstart.html">Start the quickstart</a>
      <a class="dts-button" href="./project-guide.html">Open the project guide</a>
      <a class="dts-button" href="./concepts/local-first-safety.html">Read the safety model</a>
    </div>
  </div>
  <div class="dts-deck" aria-label="Decorative DJ analysis console">
    <div class="dts-deck-top"><span>SQLite crate</span><span>local signal path</span></div>
    <div class="dts-record" aria-hidden="true"></div>
    <div class="dts-waveform" aria-hidden="true">
      <span></span><span></span><span></span><span></span><span></span><span></span>
      <span></span><span></span><span></span><span></span><span></span><span></span>
      <span></span><span></span><span></span><span></span><span></span><span></span>
    </div>
  </div>
</div>

It does not upload your collection. It does not decide what is a good mix. It helps you narrow a large folder into candidates worth hearing together.

## The Project Idea

A personal problem drives the project: a large local music folder can hide the next useful track, even when that track is already in your collection. `dj-track-similarity` tries to make that library easier to rediscover by combining tags, audio features, embeddings, text prompts, and optional personal classifiers.

The larger idea is DJ set dramaturgy. A set is not just a list of compatible tracks. It can have an opening, tension, release, chapters, and a destination. The app is meant to suggest candidates worth listening to while the DJ keeps the final musical decision.

This is a personal enthusiast project first. It does not claim expert ML or music-information-retrieval authority, and model output should be read as local ranking evidence, not truth. [Read the project idea](./concepts/project-idea.md).

## What you can do with it

<div class="dts-status-grid">
  <div><strong>Rediscover nearby tracks</strong><p>Start from a familiar track and audition a ranked neighborhood from your own collection.</p></div>
  <div><strong>Search for a sound</strong><p>Describe rhythm, texture, instruments, space, or energy when you do not have a reference track.</p></div>
  <div><strong>Draft a musical route</strong><p>Turn a few anchors into an editable sequence with a chosen energy, diversity, and tempo direction.</p></div>
  <div><strong>Reuse your own criteria</strong><p>Label a recurring personal concept and make it available as a library filter or gentle SET preference.</p></div>
</div>

<div class="dts-signal-board">
  <div class="dts-signal-copy">
    <p class="dts-kicker">Normal path</p>
    <h2>The workflow stays local</h2>
    <p>
      Start with a database and a folder scan. Add model data when needed. Search and export previews after that.
      The app gives you ranked candidates. Final track decisions still happen by ear.
    </p>
  </div>
  <ol class="dts-signal-chain">
    <li><span class="dts-step">01</span><strong>Scan</strong><span>Make the folder browsable without moving audio.</span></li>
    <li><span class="dts-step">02</span><strong>Analyze</strong><span>Prepare the sound comparisons needed for your task.</span></li>
    <li><span class="dts-step">03</span><strong>Search</strong><span>Turn tracks, words, or personal criteria into shortlists.</span></li>
    <li><span class="dts-step">04</span><strong>Export</strong><span>Take the reviewed list into the next part of your workflow.</span></li>
  </ol>
</div>

## What the app reads

- Audio paths and file stats.
- Mutagen-readable tags such as artist, title, album, genre, year, BPM, key, label, catalog number, comments, ISRC, duration, and format data.
- Decoded audio when you run analysis, preview a track, or use maintenance helpers.

## What the app writes by default

Most workflows write only local SQLite records and local reports. Scanning, Refresh Tags, analysis, search, preview, reset, clear, relocation preview, classifier scoring, and export do not modify source audio files.

The file-writing exceptions are explicit:

- MAEST genre tag apply writes the standard genre field in audio files.
- Audio Doctor apply repairs files only after dry-run state exists and exact confirmation is typed.
- Audio Dedup apply deletes confirmed duplicate candidates only after exact confirmation is typed.

Relocation apply is SQLite-only. It updates stored `tracks.path` values and does not move files.

<div class="dts-status-grid">
  <div><strong>Read-heavy by default</strong><p>Search, SET, preview, analysis, reset, and export avoid source-audio edits.</p></div>
  <div><strong>Explicit write paths</strong><p>Genre apply, Audio Doctor apply, and Audio Dedup apply are separate guarded flows.</p></div>
  <div><strong>Local artifacts</strong><p>SQLite databases, reports, logs, indexes, and classifier files stay on disk.</p></div>
</div>

## Start here

- [Quickstart](./getting-started/quickstart.md): scan, serve the UI, analyze a first batch.
- [Install](./getting-started/install.md): prerequisites, optional ML dependencies, frontend and docs builds.
- [First library](./getting-started/first-library.md): build the SQLite library and understand scan behavior.
- [First analysis](./getting-started/first-analysis.md): choose analysis by the result you want.
- [Reanalyze split SONARA storage](./workflows/reanalyze-sonara-split-storage.md): migrate schema v5 and rebuild current analysis.
- [User guide](./user-guide/index.md): daily UI work.
- [Workflows](./workflows/index.md): DJ task recipes.
- [Concepts](./concepts/index.md): scores, models, safety, and routing.
- [Tools and scripts](./tools-and-scripts/index.md) covers helper docs, including Rhythm Lab and the maintenance/report tools.
- [Reference](./reference/index.md): CLI, API, config, database, analysis, and UI facts.
- [Help](./help/index.md): symptoms, FAQ, and known limits.
