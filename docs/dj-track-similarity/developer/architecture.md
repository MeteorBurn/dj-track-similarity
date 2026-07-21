# Architecture map

> Audience: Developers orienting in the repository.
> Goal: See main components and data flow without reading every module first.
> Type: explanation

## Map

```mermaid
flowchart LR
    CLI[Typer CLI] --> DB[LibraryDatabase]
    API[FastAPI backend] --> DB
    UI[React frontend] --> API
    Audio[Audio files] --> Sonara[SONARA / Symphonia]
    Audio --> FFmpeg[FFmpeg shared ML decode]
    Sonara --> Queue[Sequential analysis queue]
    FFmpeg --> Queue
    Queue --> DB
    DB --> Classifiers[Manifest-ready classifier stage]
    Classifiers --> Queue
    DB --> Search[Search and SET builders]
    Lab[Rhythm Lab] --> DB
```

## Code map

- `database.py`, `db_schema.py`, `db_storage.py`, and `db_analysis*.py` cover the Core and attached sidecar schemas. These modules also handle analysis persistence, signature queries, caches, resets, and clear.
- `scanner.py`: supported audio discovery and Mutagen metadata reads.
- `analysis_queue.py`: one sequential worker shared by manual and pipeline analysis stages.
- `analysis_jobs.py` and `sonara_features.py`: separate ML jobs and native batched SONARA capture/storage.
- `analysis_pipeline.py`: fixed SONARA, ML, CLASSIFIERS parent/child orchestration.
- `sonara_contract.py`: version, schema, profile, signature, and current-analysis compatibility.
- `tempo_resolution.py` and `track_resolution.py`: confidence-aware BPM and Camelot/key resolution.
- `search.py`, `sonara_similarity*.py`, `set_builder.py`, and `transition_diagnostics.py`: search, SET ordering, and transition-risk logic.
- `classifier_manifest.py`, `classifier_scoring.py`, and `classifier_jobs.py`: promoted artifact validation, manifest-specific readiness, aggregate progress, and database-only scoring.
- `api_routes_*.py`: FastAPI route groups.
- `frontend/src/`: API mirror and UI panels.

The selected `library.sqlite` file is Core. It keeps the MAEST, MERT, MuQ, and CLAP embeddings used
by search and ranking in one indexed `embeddings` table. Complete SONARA time arrays live in
`library.timeline.sqlite`; the optional SONARA embedding and fingerprint live in
`library.representations.sqlite`. Every connection attaches the matching pair and verifies one shared
catalog ID. Hot search rows keep lightweight SONARA fields and two field-name manifests; search, SET,
and classifier scoring never load Timeline payloads.
