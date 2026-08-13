---
type: "path_query"
date: "2026-08-13T17:30:00.477316+00:00"
question: "Trace AnalysisOutput through ClassifierScorer to classifier_scores"
contributor: "graphify"
outcome: "useful"
source_nodes: ["AnalysisOutput", "classifier_scoring.py", "ClassifierScorer", ".score_rows()", "ClassifierScoreWrite", ".save_classifier_scores()", "_validate_classifier_score()", "_upsert_classifier_score()", "ClassifierScoreRecord"]
---

# Q: Trace AnalysisOutput through ClassifierScorer to classifier_scores

## Answer

Expanded via graph vocabulary: [analysis, output, classifier, scorer, scores]. The graphify matcher found a two-hop shortest label path AnalysisOutput --uses [INFERRED]--> ClassifierScoreRecord --rationale_for [EXTRACTED]--> the rationale node "Classifier score row from the classifier_scores table", which bypasses ClassifierScorer. The requested route exists, but its meaning must be separated. Fully EXTRACTED structural linkage is AnalysisOutput --imports--> classifier_scoring.py --contains--> ClassifierScorer. This proves the module imports AnalysisOutput and defines the scorer, not that AnalysisOutput is directly passed into it. The fully EXTRACTED score persistence chain is ClassifierScorer --method--> .score_rows() --references generic_arg--> ClassifierScoreWrite --references generic_arg--> .save_classifier_scores() --calls--> _validate_classifier_score() and _upsert_classifier_score(); _upsert_classifier_score() references ClassifierScoreRecord, whose rationale identifies a row of classifier_scores. The target table is represented by a rationale node rather than a standalone SQL table node. graph.json is directed=false, so relation/context labels provide the available direction evidence.

## Outcome

- Signal: useful

## Source Nodes

- AnalysisOutput
- classifier_scoring.py
- ClassifierScorer
- .score_rows()
- ClassifierScoreWrite
- .save_classifier_scores()
- _validate_classifier_score()
- _upsert_classifier_score()
- ClassifierScoreRecord