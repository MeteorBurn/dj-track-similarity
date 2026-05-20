# MAEST Multi-Window Benchmark

This note documents the MAEST `3x30` calibration check. The main MAEST adapter
now uses the same three-window averaging idea for production genre analysis, but
the benchmark script remains useful for read-only reports and before/after
inspection.

## Goal

The earlier MAEST analysis stored the top genre labels from one 30-second model
input taken from the 60-90 second section of a track. That could over-label a
track as broken, electro, or garage if the selected window happened to contain a
short rhythmic detail that was not representative of the full track.

The benchmark compares stored labels with a temporary three-window consensus:

- first window: `60s`
- second window: `38%` of track duration
- third window: `72%` of track duration

Each window is 30 seconds because the active MAEST model is
`discogs-maest-30s-pw-129e-519l`.

## Script

```powershell
python scripts\benchmark_maest_multiwindow.py `
  --db "E:\Projects\dj-track-similarity\dj-track-similarity.sqlite" `
  --limit 125 `
  --device auto `
  --top-k 8 `
  --window-batch-size 24 `
  --output "outputs\maest_multiwindow_125.json"
```

The script is read-only with respect to SQLite. It reads stored MAEST labels,
runs temporary inference, and writes only the requested JSON report. The normal
`analyze-genres` path writes the same compact `maest_genres` shape as before:
three labels and their averaged confidence scores, with no extra diagnostics.

## Local 125-Track Check

On the default local database, the first benchmark run used 125 selected tracks
with a bias toward existing syncopated/broken MAEST labels.

Results:

- device: `cuda`
- processed windows: `374`
- elapsed time: about `75s`
- errored tracks: `0`
- top-1 genre changed: `44/125` tracks (`35.2%`)
- broken/syncopated top-1 count stayed flat: `57 -> 57`
- tracks moving into broken/syncopated top-1: `13`
- tracks moving out of broken/syncopated top-1: `13`

The useful signal was not a simple increase in broken labels. The three-window
pass appears to reduce some false broken labels by checking whether that
rhythmic signal is stable across the track. It also lowers average top-1
confidence slightly because multiple windows can disagree.

## Interpretation

The benchmark suggested that `3x30` is useful because it can reduce false
single-window genre spikes while keeping the stored output simple.

The production behavior intentionally keeps only three final labels, computed
from averaged per-label activation scores across windows. Extra diagnostics such
as window support, score variance, and window disagreement are not stored in
SQLite for now; they stay in benchmark/reporting workflows only.
