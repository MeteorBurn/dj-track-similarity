---
layout: page
title: DJ Track Similarity
aside: false
---

<!-- markdownlint-disable MD033 MD041 -->

<section class="dts-hero" aria-labelledby="dts-hero-title">
  <div class="dts-hero-copy">
    <h1 id="dts-hero-title">DJ Track Similarity</h1>
    <p class="dts-hero-lead">
      Local DJ library analysis for building searchable crates, checking
      similar tracks, and preparing set ideas without uploading audio.
    </p>
    <div class="dts-hero-actions" aria-label="Primary documentation paths">
      <a
        class="dts-button dts-button-brand"
        href="/docs/getting-started/quickstart.html"
      >Start here</a>
      <a class="dts-button" href="/docs/user-guide/">Use the UI</a>
      <a class="dts-button" href="/docs/reference/">Reference</a>
    </div>
  </div>
  <div class="dts-hero-console" aria-label="Local workflow preview">
    <div class="dts-console-topline">
      <span>local session</span>
      <strong>safe by default</strong>
    </div>
    <div class="dts-console-row is-active">
      <span>scan</span>
      <strong>tags -> SQLite</strong>
    </div>
    <div class="dts-console-row">
      <span>analyze</span>
      <strong>SONARA / MERT / CLAP / MAEST</strong>
    </div>
    <div class="dts-console-row">
      <span>audition</span>
      <strong>seed search, text search, SET preview</strong>
    </div>
    <div class="dts-console-footer">
      <span>audio files</span>
      <strong>unchanged unless you choose an explicit write workflow</strong>
    </div>
  </div>
</section>

<section class="dts-workbench" aria-labelledby="dts-workbench-title">
  <div class="dts-workbench-copy">
    <p class="dts-eyebrow">Local workflow surface</p>
    <h2 id="dts-workbench-title">From crate to shortlist, with the risky steps
      separated.</h2>
    <p>
      The docs are organized around the workbench you actually use: scan a
      small folder, analyze what is missing, audition candidates, then export a
      reviewed list. File writes and deletes stay outside the normal path.
    </p>
  </div>
  <ol class="dts-signal-chain" aria-label="Main documentation workflow">
    <li>
      <span class="dts-step">01</span>
      <strong>Scan</strong>
      <span>tags -> SQLite</span>
    </li>
    <li>
      <span class="dts-step">02</span>
      <strong>Analyze</strong>
      <span>SONARA / MERT / CLAP / MAEST</span>
    </li>
    <li>
      <span class="dts-step">03</span>
      <strong>Audition</strong>
      <span>seed search and SET preview</span>
    </li>
    <li>
      <span class="dts-step">04</span>
      <strong>Export</strong>
      <span>reviewed playlist or report</span>
    </li>
  </ol>
</section>

<section class="dts-status-board" aria-label="Documentation safety boundaries">
  <div>
    <span class="dts-status-label">Normal path</span>
    <strong>Read-only toward audio</strong>
    <p>Browse, preview, search, SET, reset, and export do not rewrite source
      files.</p>
  </div>
  <div>
    <span class="dts-status-label">Explicit write</span>
    <strong>Genre tags only</strong>
    <p>MAEST genre labels can be written only through the documented tag-write
      workflow.</p>
  </div>
  <div>
    <span class="dts-status-label">Maintenance</span>
    <strong>Dry-run before apply</strong>
    <p>Repair and dedup workflows start with reports and keep apply modes
      separate.</p>
  </div>
</section>

## What this project is

`dj-track-similarity` is a local-first tool for DJs, music collectors, and
power users who work with local audio files. It scans your library into a
SQLite database, runs optional audio analysis, and gives you a browser UI for
browsing, searching, building temporary set ideas, and exporting playlists.

It is a personal enthusiast project, not a polished commercial product and not
a formal research benchmark. Treat scores as useful ranking hints, then make
the musical decision yourself.

## Where to go first

| If you want to... | Start with |
| --- | --- |
| install and see the UI | [Quickstart](getting-started/quickstart.md) |
| understand the safety model | [Local-first safety](concepts/local-first-safety.md) |
| browse and search from the UI | [User guide](user-guide/index.md) |
| prepare a set idea | [Prepare a set](workflows/prepare-a-set.md) |
| use CLI/API/database details | [Reference](reference/index.md) |
| fix common setup issues | [Troubleshooting](help/troubleshooting.md) |

## The normal path

```mermaid
flowchart LR
    A[Choose a local music folder] --> B[Scan file tags into SQLite]
    B --> C[Run selected analysis families]
    C --> D[Search by seed, features, text, or classifier scores]
    D --> E[Review a preview in the UI]
    E --> F[Export a temporary playlist]
```

Scanning and analysis create local database state. Search and Smart Set Builder
produce previews. Export writes playlist/report files. Source audio stays
unchanged unless you choose a documented tag-writing, repair, or duplicate
apply workflow.
