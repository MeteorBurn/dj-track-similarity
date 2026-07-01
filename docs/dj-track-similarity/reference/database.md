# Database reference

> Audience: Developers and power users inspecting SQLite state.
> Goal: Understand current tables and what writes them.
> Type: reference

## Core tables

| Table | Purpose |
| --- | --- |
| `tracks` | paths, file facts, display tags, analysis flags, metadata JSON |
| `embeddings` | MERT, MAEST, and CLAP vectors keyed by track and embedding key |
| `library_settings` | app settings and promoted score profile payloads |
| `track_classifier_scores` | promoted classifier scores scoped by classifier key |
| `track_likes` | liked-track state |
| `track_search_fts` | full-text search support |

## Evaluation tables

`search_sessions`, `search_result_events`, `track_pair_feedback`, `transition_feedback`, and `calibration_runs` support local evaluation and feedback.

## Write boundary

Keep app writes routed through `LibraryDatabase` with the shared lock, WAL, and busy timeout.
