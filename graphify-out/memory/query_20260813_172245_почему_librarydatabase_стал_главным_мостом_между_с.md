---
type: "query"
date: "2026-08-13T17:22:45.926289+00:00"
question: "Почему LibraryDatabase стал главным мостом между сообществами?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["LibraryDatabase", "AppDatabaseState", "_hydrate_similarity_results()", "_db()", "build_risk_penalty_sweep_report()", "load_classifier_requirements()", "run_report()"]
---

# Q: Почему LibraryDatabase стал главным мостом между сообществами?

## Answer

Expanded from original query via graph vocabulary: [library, database]. The AST LibraryDatabase node at src/dj_track_similarity/database.py:L32 is the strongest cross-community hub: degree 360 and report betweenness centrality 0.126. Of 360 incident edges, 324 leave its own community and reach 67 external communities. Tests contribute 211 edges, but the conclusion remains after filtering: 149 non-test edges span 44 communities; the strict non-test EXTRACTED subset has 90 edges across 31 communities and 23 files. The structural reason is convergence: database lifecycle and state, CLI access, API search hydration, evaluation and reporting, classifier jobs and scoring, and standalone tools all reference the same LibraryDatabase boundary. Confidence split is 290 EXTRACTED and 70 INFERRED, so inferred uses are supporting evidence rather than confirmed call relationships. The graph contains a second documentation concept also labeled LibraryDatabase with degree 3; this trace refers to the AST class node, not the docs concept.

## Outcome

- Signal: useful

## Source Nodes

- LibraryDatabase
- AppDatabaseState
- _hydrate_similarity_results()
- _db()
- build_risk_penalty_sweep_report()
- load_classifier_requirements()
- run_report()