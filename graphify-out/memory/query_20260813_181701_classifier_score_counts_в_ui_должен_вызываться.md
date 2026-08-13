---
type: "query"
date: "2026-08-13T18:17:01.386885+00:00"
question: "classifier_score_counts в UI должен вызываться"
contributor: "graphify"
outcome: "corrected"
correction: "classifier_score_counts is called by the nested GET /api/classifiers handler in api_routes_analysis.py; the current graph omits that direct caller-edge because nested route handlers are collapsed."
source_nodes: ["register_analysis_routes()", ".classifier_score_counts()", "api", "SearchPlaylistPanel.tsx", "formatClassifierScoredTracks()"]
---

# Q: classifier_score_counts в UI должен вызываться

## Answer

Expanded from original query via graph vocab: [classifier, scores, counts, track, tracks, frontend, display, range, control, panel, profiles, api]. Correction: source inspection proves the UI path already exists. GET /api/classifiers calls LibraryDatabase.classifier_score_counts, returns scored_tracks per profile, frontend api.classifiers fetches it, App adopts profiles, and SearchPlaylistPanel displays formatClassifierScoredTracks(scoredTracks). The missing graph caller-edge is an AST extraction limitation for nested route handlers, not an absent implementation. Focused backend and frontend tests pass.

## Outcome

- Signal: corrected
- Correction: classifier_score_counts is called by the nested GET /api/classifiers handler in api_routes_analysis.py; the current graph omits that direct caller-edge because nested route handlers are collapsed.

## Source Nodes

- register_analysis_routes()
- .classifier_score_counts()
- api
- SearchPlaylistPanel.tsx
- formatClassifierScoredTracks()