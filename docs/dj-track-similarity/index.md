<div class="dts-hero">
  <div class="dts-hero-copy">
    <p class="dts-kicker">Local crate intelligence</p>
    <h1>Find the next track without giving up your library</h1>
    <p class="dts-hero-lead">
      <code>dj-track-similarity</code> is a local-first DJ library workbench. Scanned tags,
      analysis signals, search results, and set previews stay on your machine.
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
    <li><span class="dts-step">01</span><strong>Scan</strong><span>Read file tags into SQLite.</span></li>
    <li><span class="dts-step">02</span><strong>Analyze</strong><span>Store SONARA, MAEST, MERT, and CLAP signals.</span></li>
    <li><span class="dts-step">03</span><strong>Search</strong><span>Use seeds, prompts, classifiers, and SET previews.</span></li>
    <li><span class="dts-step">04</span><strong>Export</strong><span>Write M3U or CSV after listening.</span></li>
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
- [First analysis](./getting-started/first-analysis.md): choose SONARA, MAEST, MERT, CLAP, and classifier jobs.
- [User guide](./user-guide/index.md): daily UI work.
- [Workflows](./workflows/index.md): DJ task recipes.
- [Concepts](./concepts/index.md): scores, models, safety, and routing.
- [Tools and scripts](./tools-and-scripts/index.md) covers helper docs, including Rhythm Lab and the maintenance/report tools.
- [Reference](./reference/index.md): CLI, API, config, database, analysis, and UI facts.
- [Help](./help/index.md): symptoms, FAQ, and known limits.
