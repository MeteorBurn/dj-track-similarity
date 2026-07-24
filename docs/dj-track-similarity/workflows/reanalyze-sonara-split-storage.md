# Prepare and rebuild a SONARA release

> Audience: Users activating the current SONARA contract in a schema-v7 library.
> Goal: Back up the bundle, activate one strict release, and rebuild SONARA-dependent results.
> Type: workflow

This workflow starts from a fresh schema-v7 bundle. It is not a path for upgrading a v6 database:
the runtime rejects non-v7 schemas, and the former `migrate-v7` and `migrate-schema-v7` commands are
gone.

## 1. Confirm the bundle

Selecting a new Core path creates:

```text
library.sqlite
library.artifacts.sqlite
```

The optional `library.evaluation.sqlite` file appears only when an evaluation workflow needs it.
Core and Artifacts are mandatory and share one `catalog_uuid`.

## 2. Fix runtime preflight first

SONARA and model adapters fail closed when their loaded identity differs from the locked contract.
The ML extra pins `transformers==5.13.0` and `huggingface-hub==1.22.0`. Synchronize the environment
before ML analysis. Do not bypass the preflight.

Verify SONARA separately:

```powershell
python -c "import sonara; print(sonara.__version__)"
```

The expected package version is `0.3.1`.

## 3. Prepare the release

Create an existing writable backup directory, stop competing work on the selected database, and run:

```powershell
dj-sim prepare-sonara-release --db .\data\library.sqlite --backup-dir .\backup --confirm "PREPARE SONARA RELEASE"
```

The command derives the loaded runtime identity and all four outputs: `core`, `timeline`,
`embedding`, and `fingerprint`. It does not accept a caller-provided release hash or output subset.
It verifies a Core plus Artifacts backup pair and advances an ordered, receipt-backed activation.
Interrupted work can resume; mismatched catalog, backup, receipt, or runtime identity fails closed.

Preparation removes previous SONARA rows and SONARA-dependent classifier scores before activating
the new contracts. It preserves non-SONARA embeddings, labels, feedback, likes, and audio files.

## 4. Run a bounded pilot

Start with familiar files:

```powershell
dj-sim analyze --models sonara --sonara-outputs core,timeline,embedding,fingerprint --limit 100 --db .\data\library.sqlite
```

The current contract is SONARA `0.3.1`, upstream schema `5`, playlist mode, sample rate `22050`, BPM
range `70..180`, and project feature revision `6`. The default native batch size is `8`;
`--sonara-batch-size` accepts `1..16`.

A successful pilot is a stop point for review, not permission to start a full-library run. Review
job failures and representative search results. Then verify database integrity before deciding
whether to continue.

## 5. Complete the selected outputs

After explicit approval for the larger run, omit `--limit`:

```powershell
dj-sim analyze --models sonara --sonara-outputs core,timeline,embedding,fingerprint --db .\data\library.sqlite
```

`core` is always included. Optional outputs can be requested later, and scheduling checks each exact
contract independently.

## 6. Retrain and promote classifiers

The runtime accepts classifier manifest version `2`. The promoted artifacts currently checked into
`models/classifiers/` use version `1`, so scoring is blocked. After required analysis coverage is
complete, retrain and promote each affected profile, then run:

```powershell
dj-sim analyze-classifiers --db .\data\library.sqlite
```

The scoring job reads stored inputs only and writes compatible classifier-track pairs. It does not
decode or modify audio.

## 7. Use the current surface

The backend and CLI use the v7 contract. The React frontend port is explicitly deferred, so
do not use current UI behavior as proof that the v7 API is ready. Validate with CLI output, API
responses, focused tests, and direct SQLite integrity checks.
