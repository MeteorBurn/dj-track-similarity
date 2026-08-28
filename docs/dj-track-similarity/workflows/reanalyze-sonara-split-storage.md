# Reanalyze SONARA data

Reanalysis is a separate user decision. Nothing here happens automatically, and normal startup never
rewrites a legacy split database. To convert that layout, stop every SQLite user and run
`dj-sim migrate-database --db .\data\library.sqlite --confirm 'MIGRATE SINGLE LIBRARY'`. It creates
a backup and does not start reanalysis.

## 1. Back up the library

Stop jobs and other writers. Copy `library.sqlite`, and include `library.evaluation.sqlite` if it
exists. Verify SQLite integrity on the backup before proceeding.

## 2. Choose the data to rebuild

A SONARA release does not force a project-wide reset. Change only the stored fields and analysis
behavior you intend to use. If a classifier recipe depends on changed SONARA features, plan to
retrain, promote, and rescore that classifier afterwards.

If the Core row already exists but the dedicated SONARA embedding row is missing, a normal SONARA
run can backfill it without a reset. The track is selected because one output is missing, then all
three outputs are written together.

## 3. Reset SONARA when chosen

Press the trash icon on the `SONARA` row in panel `1. База и анализ` (database and analysis), or
call `POST /api/analysis/reset` with `{"analysis_family": "sonara"}`. The CLI has no reset command.

The reset deletes `sonara_features` Core rows only. It keeps:

- the dedicated 48-dimensional SONARA embedding rows,
- the acoustic fingerprint rows,
- every row in `classifier_scores`,
- Rhythm Lab labels and feedback.

Reset changes SQLite data only. It does not touch audio files and does not start a new analysis job.

Resetting SONARA is also the way to change the library BPM range. The range is fixed by the first
SONARA analysis, and any later job requesting a different pair is refused until the reset clears the
stored rows.

## 4. Run a bounded pilot

Start with familiar files:

```powershell
dj-sim analyze --models sonara --limit 100 --db .\data\library.sqlite
```

Review failures and representative search results before deciding whether to continue.

## 5. Complete the intentional reanalysis

Omit `--limit` only after approving a full-library run:

```powershell
dj-sim analyze --models sonara --db .\data\library.sqlite
```

SONARA writes Core rows to `sonara_features`, unnormalized 48-dimensional `float32` embeddings to
the dedicated `sonara_embeddings` table, and versioned native-base64 acoustic fingerprints to
`sonara_fingerprints`. Each successful pass writes all three outputs together under one per-track
savepoint. Timeline collection remains disabled.

The stored embedding is not a current similarity, search, classifier, or Audio Dedup input. The
stored fingerprint feeds only Audio Dedup candidate retrieval and manual review.

A SONARA batch failure fails the whole job, so review the log before restarting a long run.

## 6. Refresh affected classifiers

When the changed SONARA data affects an ordered classifier feature recipe, retrain and promote that
classifier in Rhythm Lab first. See
[Train a personal classifier](./train-personal-classifier.md).

Then reset the classifier key and rescore it:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/classifiers/reset -Method Post -ContentType 'application/json' -Body '{"classifier_key":"live_instrumentation"}'
dj-sim analyze-classifier live_instrumentation --db .\data\library.sqlite
```

The reset is required. Classifier scoring is incremental: its candidate query excludes every track
that already has a row for that key, so rescoring without a reset finds zero work and leaves the
stale scores in place. The play button on a `CLASS` row does both steps in one press.

Classifier scoring reads stored inputs and writes database scores. It does not decode or modify
source audio.
