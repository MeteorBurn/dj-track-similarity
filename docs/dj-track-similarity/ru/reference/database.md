# Database reference

Аудитория: developers и осторожные power users  
Цель: описать current SQLite storage model  
Тип: reference

Main library database - SQLite. Schema writes handled by project database
layer, который configures WAL and busy timeout and serializes writes per
database path.

## Current schema version

Current library schema version is `4`.

## Core tables

| Table | Purpose |
| --- | --- |
| `tracks` | paths, tags, derived fields, metadata JSON, analysis flags |
| `embeddings` | vector embeddings keyed by track and embedding key |
| `library_settings` | small database-scoped settings |
| `track_classifier_scores` | promoted classifier scores by track and key |
| `track_likes` | user liked-track state |
| `track_search_fts` | full-text search support |

`embeddings` table uses `(track_id, embedding_key)` as primary key. Classifier
scores scoped by `(track_id, classifier)`.

## Track fields

Track rows include stored path, artist, title, album, BPM, musical key, energy,
duration, analysis availability flags and `metadata_json`.

Stored `metadata_json` must remain JSON-safe.

## What not to edit manually

Avoid hand-editing embeddings, classifier scores, search FTS rows and schema
metadata. Use project commands or focused helper scripts so indexes and caches
stay coherent.

## Local user state

Treat project SQLite files as local user state. Tests should use temporary
databases, not a real music-library database.
