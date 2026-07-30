# Migrate and reanalyze SONARA storage

> Audience: Users adopting SONARA or database-structure changes.
> Goal: Preview and back up structural changes, then rebuild only the analysis you choose.
> Type: workflow

Normal application startup never migrates or adapts an incompatible database. It refuses the
Core/Artifacts pair with a clear message. Migration and reanalysis are separate, explicit
decisions.

## 1. Confirm the bundle

A selected library consists of:

```text
library.sqlite
library.artifacts.sqlite
```

The optional `library.evaluation.sqlite` appears only when an evaluation workflow needs it. Core and
Artifacts are mandatory and share one `catalog_uuid`.

Stop jobs and other writers before maintenance. Keep the current files together.

## 2. Preview the migration

The dry run opens Core, Artifacts, and any existing Evaluation database read-only. It reports the
tables that would be rebuilt or excluded and the analysis families that may need reanalysis:

```powershell
dj-sim migrate-database --db .\data\library.sqlite --dry-run
```

Review the exact paths, structural changes, warnings, and suggested backup location. A dry run does
not create backups, write SQLite, or start analysis.

## 3. Apply only after review

Rerun without `--dry-run` when you accept the plan:

```powershell
dj-sim migrate-database --db .\data\library.sqlite
```

Type the exact confirmation:

```text
MIGRATE DATABASE
```

You can use `--backup-dir` to select a different backup directory. Before replacing either database,
the command creates self-contained Core and Artifacts backups and validates their integrity together
with the shared catalog identity. A final source check confirms that the files still match the
reviewed plan.

The command rebuilds the pair under exclusive SQLite locks and finishes with integrity,
foreign-key, and orphan checks. A controlled failure restores the verified backup pair. If a process
crashes between the two database publications, normal startup refuses the pair and points back to
the recorded recovery and backup paths.

Evaluation is inspected for warnings but is not rewritten by this migration.

## 4. Review the receipt

Keep the reported Core and Artifacts backup paths until the migrated library has been checked. The
receipt also reports excluded legacy rows and analysis families that may need new results.

Migration does not decide whether reanalysis is desirable. It does not start SONARA, ML, or
classifier jobs.

## 5. Run a bounded SONARA pilot when chosen

After the migrated database opens normally, start with familiar files:

```powershell
dj-sim analyze --models sonara --limit 100 --db .\data\library.sqlite
```

When you choose to update SONARA, adapt the project and use focused checks for the new Core fields
and capabilities without defining an optional-output version contract.

Review failures and representative search results before deciding whether to continue.

## 6. Complete Core analysis

Omit `--limit` only after approving a full-library run:

```powershell
dj-sim analyze --models sonara --db .\data\library.sqlite
```

SONARA writes Core only. Timeline, SONARA embedding, and fingerprint collection remain disabled.

## 7. Retrain affected classifiers

When a SONARA update changes a classifier's ordered feature recipe, reuse the preserved Rhythm Lab
profiles and labels to retrain and promote only that affected classifier. Then run:

```powershell
dj-sim analyze-classifiers --db .\data\library.sqlite
```

Classifier scoring reads stored inputs and writes database scores. It does not decode or modify
source audio.
