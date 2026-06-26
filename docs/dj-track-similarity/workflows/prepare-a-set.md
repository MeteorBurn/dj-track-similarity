# Prepare a set

Audience: DJs using the browser UI  
Goal: turn a few tracks into a reviewed export  
Type: tutorial

This workflow starts with tracks you trust, creates candidates, builds a
preview, and exports only after you review the result.

## Before you start

You need a scanned library and enough analysis for the search mode you plan to
use:

- SONARA features for explainable feature search;
- MERT embeddings for audio seed similarity;
- CLAP embeddings for text prompts;
- SONARA, MERT, MAEST, and CLAP for Smart Set Builder.

## 1. Pick the first anchors

In the library table, find one to five tracks that represent the sound you want.
Avoid picking several tracks by the same known artist if you plan to use Smart
Set Builder, because the SET route keeps a strict artist guard.

## 2. Search around the anchors

Use the search tab that matches the job:

| Need | Tab |
| --- | --- |
| similar audio feel from selected tracks | `MERT` |
| explainable musical features | `SONARA` |
| text prompt such as "dark rolling techno" | `CLAP` |
| ordered set preview | `SET` |
| promoted personal concept | `CLASS` |

Add only tracks you want to audition. Search results are candidates, not a
finished set.

## 3. Generate a SET preview

Open `SET`, choose `Manual` or `Auto`, set the track limit, energy curve,
diversity, and BPM mode, then generate a preview.

The preview is read-only. It becomes part of the current set only when you use
the explicit add action.

## 4. Listen and remove weak links

Use preview playback, metadata, BPM/key, and your own judgement. Similarity
scores are ranking hints; they do not know the room, crowd, or transition
style.

## 5. Export

When the current set looks useful, export it as a playlist/report from the UI.
Export writes playlist/report files. It does not rewrite source audio.
