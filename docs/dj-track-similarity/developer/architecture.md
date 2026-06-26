# Architecture

Audience: developers and maintainers  
Goal: describe the main runtime pieces  
Type: explanation/reference

The project is a Python backend/CLI with a React/Vite frontend and a separate
Rhythm Lab helper app.

## Backend

Important modules:

- `database.py`: SQLite access, write serialization, summaries, relocation,
  resets, caches, and stored analysis state.
- `scanner.py`: supported audio discovery and Mutagen metadata extraction.
- `audio_loader.py`: shared decoding path.
- `sonara_features.py` and `sonara_jobs.py`: SONARA extraction and jobs.
- `genres.py` and `genre_jobs.py`: MAEST genre analysis jobs.
- `embedding.py` and `analysis_jobs.py`: MERT/CLAP embeddings and analysis
  orchestration.
- `classifier_scoring.py` and `classifier_jobs.py`: promoted classifier
  scoring and jobs.
- `search.py` and `sonara_similarity.py`: embedding and SONARA search.
- `api.py` and `cli.py`: FastAPI and Typer entrypoints.

## Frontend

The main UI lives under `frontend/`. `frontend/src/api.ts` mirrors backend API
contracts used by React components.

The production backend serves `frontend/dist` when it exists. Run the frontend
build after frontend source changes.

## Rhythm Lab

Rhythm Lab is under `tools/rhythm-lab/`. It has its own lab UI, CLI, labels
database, training artifacts, and promotion path. Runtime promoted models for
the main app live separately under `models/classifiers/`.

## Docs

The VitePress docs live under `docs/dj-track-similarity` and build to `site`.
The main backend mounts that generated directory at `/docs`.
