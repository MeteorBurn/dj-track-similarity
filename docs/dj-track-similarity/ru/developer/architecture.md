# Architecture

Аудитория: developers and maintainers  
Цель: describe main runtime pieces  
Тип: explanation/reference

Project is Python backend/CLI with React/Vite frontend and separate Rhythm Lab
helper app.

## Backend

Important modules:

- `database.py`: SQLite access, write serialization, summaries, relocation,
  resets, caches and stored analysis state.
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

Main UI lives under `frontend/`. `frontend/src/api.ts` mirrors backend API
contracts used by React components.

Production backend serves `frontend/dist` when it exists. Run frontend build
after frontend source changes.

## Rhythm Lab

Rhythm Lab is under `tools/rhythm-lab/`. It has its own lab UI, CLI, labels
database, training artifacts and promotion path. Runtime promoted models for
main app live separately under `models/classifiers/`.

## Docs

VitePress docs live under `docs/dj-track-similarity` and build to `site`. Main
backend mounts generated directory at `/docs`.
