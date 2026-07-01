# Database

> Audience: Пользователи этой страницы.
> Type: how-to

Core tables: `tracks`, `embeddings`, `library_settings`, `track_classifier_scores`, `track_likes`, `track_search_fts`. Evaluation tables: `search_sessions`, `search_result_events`, `track_pair_feedback`, `transition_feedback`, `calibration_runs`. App writes should go through `LibraryDatabase` with shared write lock, WAL and busy timeout.
