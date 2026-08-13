---
type: "path_query"
date: "2026-08-13T17:25:57.834247+00:00"
question: "Path from LibraryDatabase to AnalysisOutput"
contributor: "graphify"
outcome: "useful"
source_nodes: ["LibraryDatabase", "_search_source()", "AnalysisOutput", "AnalysisRepository", "classifier_scoring.py", "candidates.py"]
---

# Q: Path from LibraryDatabase to AnalysisOutput

## Answer

Expanded via graph vocabulary: [library, database, analysis, output]. The CLI path matcher first selected the ambiguous documentation LibraryDatabase node and found no path. After disambiguating to the AST class node src_dj_track_similarity_database_librarydatabase, the undirected shortest path length is 2. There are 36 common neighbors; after excluding test nodes, 9 non-test shortest paths remain. The strongest semantically specific fully EXTRACTED path is LibraryDatabase --references (parameter_type)--> _search_source() at src/dj_track_similarity/evaluation/candidates.py:L328 --references (generic_arg)--> AnalysisOutput at src/dj_track_similarity/analysis_models.py:L730. A conceptually architectural alternative is LibraryDatabase --uses [INFERRED]--> AnalysisRepository at src/dj_track_similarity/db_analysis.py:L484 --uses [INFERRED]--> AnalysisOutput. The graph is directed=false, so these paths show shared structural/type relationships, not runtime call direction.

## Outcome

- Signal: useful

## Source Nodes

- LibraryDatabase
- _search_source()
- AnalysisOutput
- AnalysisRepository
- classifier_scoring.py
- candidates.py