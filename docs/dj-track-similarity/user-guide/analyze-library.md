# Analyze a library

Analysis reads source audio and writes local SQLite state. It does not modify source audio files.
Scan first, then pick the analysis family that answers your listening question.

## Browser controls

The browser can start the jobs directly. **Analyze limit** defaults to `0` for the whole eligible
library. The initial batch values are Track `8`,
Inference `16`, and SONARA `8`; **Device** defaults to `auto`.

The panel keeps **SONARA**, **ML**, and **CLASSIFIERS** as separate stages. **FULL** runs them in the
fixed order. SONARA is selected at startup and always runs Core, its dedicated embedding, and its
acoustic fingerprint as one fixed output set. There are no output checkboxes. The ML selection contains MAEST, MERT, MuQ,
MuQ-MuLan, and CLAP, not SONARA or CLASSIFIERS. The browser still starts with SONARA selected;
when the CLI or API ML model list is omitted, its normal ordered default is MAEST, MERT, MuQ,
MuQ-MuLan, then CLAP. Progress, per-file failures, blockers, cancellation, and reset
results come from the typed job responses.

## What happens after you press Analyze

A started job loads its models before it reads the first track. For that stretch the process box
shows a warm-up view instead of per-track progress. The view has a progress bar over the number of
selected models, the current model name, and its resolved device. A line under them states that
track decoding has not begun. The stage indicator names model warm-up rather than analysis while
this lasts. When loading finishes, the usual per-track progress box replaces it and the track
counters start moving. The analysis stage of a **FULL** or pipeline run shows the same view, because
the browser follows the running stage's job.

An empty-looking gap at the start of a first run is normally this phase. Model weights download on
first use, so the first job for a family waits for that download here rather than in the middle of
track work. A model that cannot load fails the job during warm-up, before any track is read. Once a
model is loaded it stays in memory for the life of the server process, so a repeated job with the
same models, device, and batch settings passes warm-up without loading again. The job log entries
are listed in [Model warm-up](../reference/analysis-families.md#model-warm-up).

## Run a family

SONARA can run alone and writes its fixed Core, embedding, and fingerprint output set:

```powershell
dj-sim analyze --models sonara --db .\data\library.sqlite
```

ML families can run together:

```powershell
dj-sim analyze --models maest,mert,muq,mulan,clap --db .\data\library.sqlite
```

Omit `--limit` to consider the whole library. A positive limit selects only candidates missing the
requested current outputs. Use `--device auto`, `--device cpu`, or `--device cuda` for MAEST, MERT,
MuQ, MuQ-MuLan, and CLAP. SONARA uses its native CPU path.

## SONARA storage

SONARA writes Core feature rows to `sonara_features`, unnormalized 48-dimensional `float32`
embeddings to the dedicated `sonara_embeddings` table, and versioned native-base64 acoustic
fingerprints to `sonara_fingerprints`. A successful SONARA pass stores all three rows together.
Timeline collection remains disabled. The SONARA embedding and fingerprint are persisted data only;
they are not current UI, similarity, search, classifier, or Audio Dedup inputs. MAEST, MERT, MuQ,
MuQ-MuLan, and CLAP embeddings live in their own dedicated tables in the same library database.
MuQ-MuLan analysis reads mono 24 kHz `float32` audio in 10-second windows and writes its own
L2-normalized 512-dimensional rows to `mulan_embeddings`. It never converts existing MuQ rows.

`*.evaluation.sqlite` is optional evaluation state. Normal startup refuses a legacy split layout
rather than adapting it automatically.

## Reanalyze after a SONARA change

Adopting a new SONARA release does not require a versioned project contract. Adapt the fields and
storage that the project should use. Reanalysis is a separate choice: use **Reset SONARA**, then
**Analyze**, only for outputs you intend to rebuild. Retrain and promote a classifier only when its
ordered feature recipe changed.

## Pipeline and classifiers

The backend pipeline order is SONARA, then ML. Per-file failures are kept in job status. A fatal
initialization failure or cancellation stops later stages.

Classifier scoring is database-only and does not decode source audio. Start it for one promoted
profile from the **CLASS** tab. It requires ordered feature names and inputs that match current
stored data. An incompatible artifact is blocked until that profile is retrained and promoted.
Scores stay scoped to their `classifier_key`.

## Reset and interpretation

Resets affect SQLite data only. A normal SONARA rerun selects a track when any current Core,
embedding, or fingerprint row is missing and stores all three rows together. Tracks with all three
rows remain skipped. Use **Reset SONARA**, then **Analyze**, only for an intentional full
reanalysis. Model outputs are ranking evidence for listening-led shortlists, not objective truth or
automatic DJ decisions.
