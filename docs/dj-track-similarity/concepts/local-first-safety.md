# Local-first safety model

> Audience: Users and developers checking write boundaries.
> Goal: Explain what writes SQLite, reports, audio tags, or deletes files.
> Type: explanation

## Model

Normal app workflows read audio and write SQLite state. Only named exceptions touch source audio or delete files.

## Map

```mermaid
flowchart TD
    A[Scan, Refresh Tags, analysis] --> B[SQLite updates]
    C[Search and SET preview] --> D[Browser/API response]
    E[Export] --> F[M3U or CSV]
    G[Genre apply] --> H[Audio genre tag]
    I[Audio Doctor apply] --> J[Repairable audio file]
    K[Audio dedup apply] --> L[Confirmed duplicate delete]
```

## Relocation

Relocation apply updates stored `tracks.path` values only after missing-file and conflict checks pass.
