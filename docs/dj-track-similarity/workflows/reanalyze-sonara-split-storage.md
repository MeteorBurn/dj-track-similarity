# Reanalyze SONARA data

> Audience: Users adopting a SONARA update or changing the analysis they store.
> Goal: Back up the library and rebuild only the data you choose.
> Type: workflow

Normal startup never rewrites a legacy split database. To convert that layout, stop every SQLite
user and run `dj-sim migrate-database --db .\data\library.sqlite --confirm 'MIGRATE SINGLE LIBRARY'`;
it creates a backup and does not start reanalysis.

## 1. Back up the library

Stop jobs and other writers. Copy `library.sqlite`, and include
`library.evaluation.sqlite` if it exists. Verify SQLite integrity on the backup before proceeding.

## 2. Choose the data to rebuild

A SONARA release does not force a project-wide reset. Change only the stored fields and analysis
behavior you intend to use. If a classifier recipe depends on changed SONARA features, plan to
retrain, promote, and rescore that classifier afterwards.

If the Core row already exists but the dedicated SONARA embedding row is missing, a normal SONARA
run can backfill it without a reset. The track is selected because one output is missing, then Core
and embedding are written together.

## 3. Reset SONARA when chosen

Use **Reset SONARA** in the browser or the matching CLI/API path. Reset changes SQLite data only;
it does not touch audio files and does not start a new analysis job.

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
`sonara_fingerprints`. Each successful pass writes all three outputs together. Timeline collection
remains disabled. The stored embedding and fingerprint are not current similarity, search,
classifier, or Audio Dedup inputs.

## 6. Refresh affected classifiers

When the changed SONARA data affects an ordered classifier feature recipe, retrain and promote that
classifier in Rhythm Lab, then run:

```powershell
dj-sim analyze-classifier <classifier_key> --db .\data\library.sqlite
```

Classifier scoring reads stored inputs and writes database scores. It does not decode or modify
source audio.
