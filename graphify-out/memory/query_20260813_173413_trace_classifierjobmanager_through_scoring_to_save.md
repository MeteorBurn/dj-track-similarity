---
type: "path_query"
date: "2026-08-13T17:34:13.568808+00:00"
question: "Trace ClassifierJobManager through scoring to save_classifier_scores"
contributor: "graphify"
outcome: "corrected"
correction: "ClassifierJobManager is confirmed to orchestrate start/create_job/run_job/_score_batch and construct ClassifierScorer. Its _Scorer interface exposes score_row(), not score_rows(); the current graph does not contain direct calls edges from _score_batch to scoring or persistence methods."
source_nodes: ["ClassifierJobManager", ".start()", ".create_job()", ".run_job()", "._score_batch()", "._make_scorer()", "_Scorer", ".score_row()", "ClassifierScorer", "ClassifierFeatureRow"]
---

# Q: Trace ClassifierJobManager through scoring to save_classifier_scores

## Answer

Expanded via graph vocabulary: [classifier, job, manager, score, scorer, rows, save]. The proposed ClassifierJobManager -> score_rows() -> save_classifier_scores() runtime chain is not confirmed by the graph. Fully EXTRACTED orchestration is start() -> create_job() and run_job(); create_job() calls _make_scorer(), which calls ClassifierScorer; run_job() calls _score_batch(). _score_batch() references _Scorer as a parameter type and ClassifierFeatureRow as a generic argument. The _Scorer protocol exposes score_row(), not score_rows(). No EXTRACTED calls edge connects _score_batch() directly to score_row(), score_rows(), or save_classifier_scores(), likely because these are dynamic attribute calls the AST graph did not resolve. The shortest manager-to-save path instead goes through ClassifierScoreWrite with one INFERRED uses edge, so it is type-level evidence, not runtime call proof. Persistence internals in save_classifier_scores remain EXTRACTED, but the handoff from ClassifierJobManager to that method is unresolved in the current graph.

## Outcome

- Signal: corrected
- Correction: ClassifierJobManager is confirmed to orchestrate start/create_job/run_job/_score_batch and construct ClassifierScorer. Its _Scorer interface exposes score_row(), not score_rows(); the current graph does not contain direct calls edges from _score_batch to scoring or persistence methods.

## Source Nodes

- ClassifierJobManager
- .start()
- .create_job()
- .run_job()
- ._score_batch()
- ._make_scorer()
- _Scorer
- .score_row()
- ClassifierScorer
- ClassifierFeatureRow
- ClassifierScoreWrite
- .save_classifier_scores()