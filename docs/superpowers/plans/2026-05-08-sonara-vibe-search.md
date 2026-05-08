# SONARA Vibe Search Plan

**Summary**
Implement SONARA-only seed search with multiple similarity modes: `Balanced`, `Vibe`, `Sound`, and `DJ transition`. The search will use stored `sonara_features` from SQLite, preserve the existing MERT/CLAP backend paths, and make SONARA search the primary seed-search workflow in the UI.

**Key Changes**
- Add a new backend module, `src/dj_track_similarity/sonara_similarity.py`, with `SonaraSimilaritySearch`.
- Add `/api/search/sonara` with request fields:
  - `seed_track_ids`
  - `lookback_track_ids`
  - `limit`
  - `mode`: `balanced | vibe | sound | dj_transition`
  - `min_similarity`
- Keep `/api/search` as existing embedding/MERT search for compatibility.
- Add `api.sonaraSearch(...)` and a search mode control in `frontend/src/api.ts`, `frontend/src/App.tsx`, and `frontend/src/SearchPlaylistPanel.tsx`.

**Similarity Design**
- Do not use `camelot_key` anywhere.
- Use raw SONARA tonal fields only:
  - `key`
  - `key_confidence`
  - `predominant_chord`
  - `chord_change_rate`
  - `dissonance`
  - `chroma_mean` summary/value when available
- Build per-track weighted feature comparisons:
  - `Vibe`: `energy`, `danceability`, `valence`, `acousticness`, loudness/dynamic/rhythm summary.
  - `Sound`: MFCC summaries, spectral centroid/bandwidth/rolloff/flatness/contrast, zero crossing, RMS.
  - `DJ transition`: BPM distance, onset density, energy/danceability, raw SONARA key/chord agreement, chord change rate, dissonance.
  - `Balanced`: weighted blend of vibe, sound, groove, and raw tonal features.
- Normalize numeric features across tracks with stored SONARA data; compare candidates to the seed/lookback centroid.
- Skip candidates with too little overlapping SONARA data instead of returning misleading matches.
- Return scores in `0.0..1.0` so the current `SearchResult` type remains usable.

**UI Behavior**
- Replace the old MERT-only seed-search note with a SONARA search note.
- Add a compact mode selector: `Balanced`, `Vibe`, `Sound`, `DJ`.
- Keep active controls focused: `Mode`, `Similarity`, `Lookback`, `Limit`.
- Keep CLAP text search separate.
- Show normal result rows using the existing score display.

**Tests**
- Add backend unit tests for:
  - `vibe` mode ranking by energy/danceability/valence/acousticness.
  - `sound` mode ranking by MFCC/spectral summaries.
  - `dj_transition` ranking by BPM/onset/raw SONARA tonal data.
  - `camelot_key` ignored even when present.
  - missing SONARA features excluded or reported cleanly.
  - seed + lookback centroid behavior.
- Add API tests for `/api/search/sonara`.
- Run:
  - `pytest`
  - `cd frontend && npm run build`

**Assumptions**
- SONARA search should become the primary seed-search action.
- MERT search remains available internally through the existing `/api/search`, but the UI seed button will call SONARA search for this feature.
- Raw SONARA tonal fields are trusted directly; Camelot conversion is not part of this workflow.
