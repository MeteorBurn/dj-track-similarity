---
type: "path_query"
date: "2026-08-13T17:37:39.977465+00:00"
question: "Trace AnalysisOutput to ClassifierFeatureRow to score_row"
contributor: "graphify"
outcome: "useful"
source_nodes: ["AnalysisOutput", "_classifier_input_query_parts()", "table_for_output()", "_classifier_feature_vector_from_row()", "_classifier_work_item_from_row()", ".load_classifier_work_batch()", "ClassifierFeatureRow", ".score_row()", ".score_rows()", "ClassifierScoreWrite"]
---

# Q: Trace AnalysisOutput to ClassifierFeatureRow to score_row

## Answer

Expanded via graph vocabulary: [analysis, output, classifier, feature, row, score, input, scorer]. The literal shortest path AnalysisOutput -> analysis_models.py -> ClassifierFeatureRow is only shared module containment and does not prove conversion. A stronger fully EXTRACTED producer path is AnalysisOutput -> _classifier_feature_vector_from_row() -> _classifier_work_item_from_row() -> ClassifierFeatureRow. _classifier_input_query_parts() builds fixed-table joins for one classifier recipe and table_for_output() selects storage per AnalysisOutput. load_classifier_work_batch() calls _classifier_input_query_parts() and _classifier_work_item_from_row(), returning ClassifierFeatureRow batches. The concrete ClassifierScorer.score_row() accepts ClassifierFeatureRow as its parameter type and returns ClassifierScoreWrite; score_rows() calls score_row(). Inside score_row(), EXTRACTED calls go to _predict_probabilities(), _argmax_with_tiebreak(), ClassifierScoreRecord(), _score_bucket_from_score(), and utc_timestamp(). The graph does not enumerate all feature-vector components; it does show a SONARA-specific resolution call through resolve_sonara_classifier_feature() and a recipe-dependent fixed-table join boundary.

## Outcome

- Signal: useful

## Source Nodes

- AnalysisOutput
- _classifier_input_query_parts()
- table_for_output()
- _classifier_feature_vector_from_row()
- _classifier_work_item_from_row()
- .load_classifier_work_batch()
- ClassifierFeatureRow
- .score_row()
- .score_rows()
- ClassifierScoreWrite
- resolve_sonara_classifier_feature()