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
    Audio[Audio files] --> Scan[Scanner and analysis jobs]
    Scan --> DB
    DB --> Search[Search and SET builders]
    Lab[Rhythm Lab] --> DB
```

## Code map

- `database.py`, `db_schema.py`, and `db_analysis*.py`: SQLite schema, analysis writes, current-signature queries, caches, resets, and clear.
- `scanner.py`: supported audio discovery and Mutagen metadata reads.
- `analysis_jobs.py` and `sonara_features.py`: cancellable multi-model jobs and SONARA capture/storage.
- `sonara_contract.py`: version, schema, profile, signature, and current-analysis compatibility.
- `tempo_resolution.py` and `track_resolution.py`: confidence-aware BPM and Camelot/key resolution.
- `search.py`, `sonara_similarity*.py`, `set_builder.py`, and `transition_diagnostics.py`: search, SET ordering, and transition-risk logic.
- `classifier_manifest.py` and `classifier_scoring.py`: promoted artifact validation and database-only scoring.
- `api_routes_*.py`: FastAPI route groups.
- `frontend/src/`: API mirror and UI panels.

Complete SONARA arrays and archival embedding/fingerprint data live in `sonara_curves`. Hot search
rows keep lightweight fields and summaries. The lazy curves API is not used by search, SET, or
classifier scoring.
