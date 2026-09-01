# Audio Dedup

Audio Dedup reads an existing SQLite library and writes JSON/XLSX/log reports by default. It uses stored analysis data, local paths, and a read-only FFmpeg decode of duplicate-group files for the spectral check below. It does not scan unknown folders outside the selected root and never modifies source audio.

Two surfaces run the same core. The CLI writes reports, and a confirmed `--apply` run deletes the
safe candidates in one. The browser dialog starts a scan, then reads a report back from disk for
copy-by-copy review. The same confirmation phrase deletes what you mark there. Both use the reports in
`tools/audio-dedup/data/reports/`, so a CLI report opens in the browser and a browser scan leaves an
XLSX workbook to download.

## Requirements

Audio Dedup needs stored audio-to-audio evidence. The available embedding sources are `mert`,
`maest`, `muq`, and `clap`. The reader accepts vectors whose dimensions, encoding, and track
identity match the current structural requirements.

When the library has saved SONARA fingerprints, Audio Dedup also uses them as an independent
candidate-retrieval signal. It reads only fingerprints whose stored `track_uuid`, positive
version, timestamp, and Base64 payload validate against the current track. A stored payload
shorter than four complete 32-bit frames is counted as a rejected row and never enters
retrieval. It does not analyse audio again or keep full fingerprint payloads on track records.

Exact fingerprint verification calls the native SONARA matcher, which needs the optional
`sonara` extra. When a shortlisted fingerprint pair reaches verification without that extra
installed, the CLI fails cleanly with exit code `2` and the message
`SONARA fingerprint verification needs the 'sonara' extra; install it or rerun with --embedding`.

The `min_similarity` value is an audio-to-audio content gate. It is not the CLAP text-search score scale, and none of these values are probabilities.

The spectral transcode check needs `ffmpeg` on `PATH`. Without it, that check is skipped with an
`ffmpeg unavailable` note while the duplicate search still runs.

## Search modes

The CLI has two mutually exclusive search modes:

- `--fingerprint` is the primary mode and the default, so a run without a mode flag behaves
  identically. Duplicates are decided from exact SONARA fingerprint matches alone, and every
  reported candidate stays manual-review.
- `--embedding` is the secondary mode and the previous default behavior. Duplicates are scored
  from the enabled embedding families with the preset gates, and exact fingerprint checks of
  embedding-shortlisted pairs still add manual-review pairs. It is the only mode that can produce
  safe delete candidates for `--apply`.

Passing both flags is a CLI argument error. `--source` and `--weight` require `--embedding`.
The JSON report records the selected mode as `search_mode`.

## Fingerprint mode

`--fingerprint` decides duplicates from stored SONARA fingerprints alone. It is the default, so
this run selects it without a mode flag:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music
```

In this mode no embeddings are loaded. Candidate retrieval uses only the version-separated
fingerprint LSH, and neither embedding signature LSH nor the duration-window fallback runs. The
exact native SONARA matcher then verifies every shortlisted pair, and only exact scores at or
above the `0.45` review threshold form duplicate groups.

When the scope holds `0` valid stored SONARA fingerprints, the run still writes its reports,
and the CLI prints a console warning that the empty report does not prove the scope has no
duplicates. Analyze SONARA first or rerun with `--embedding`.

Every candidate in a fingerprint-mode report is `REVIEW MANUALLY`. The report carries no embedding
scoring evidence, and per-pair MERT, MAEST, and content similarities stay null. Fingerprint
evidence never authorizes deletion, so `--apply` on such a report finds no safe delete candidates.
The `blocked_reasons` and `why_delete_or_review` text still states how confident the match is: a
candidate carries its exact fingerprint similarity score inline, such as "exact fingerprint match
0.987654 is strong duplicate evidence". A `0.98` match reads differently from one that only just
cleared the `0.45` review threshold, even though both stay manual-review.

`--source` or `--weight` in fingerprint mode fails before any database read, and the CLI exits
with code `2`. Fingerprint mode is the one report configuration without scoring sources. Its
report payload records `"search_mode": "fingerprint"` with `"sources": []` and `"weights": {}`,
while `fingerprint_retrieval` and the per-pair `candidate_sources` value `["fingerprint_lsh"]`
record the retrieval path.

## Browser review

Fingerprint mode never marks a candidate safe to delete, so a person deciding copy by copy is the
route to deletion there. The browser dialog is that review surface.

Open it from the library action row with **Find and review duplicates**, the copy-check icon to the
left of the clear-database button. It stays disabled while another job runs and while the library
holds no tracks. Reviewer control names here are given in English, and
[UI language](../help/ui-language.md) carries the on-screen string for each one.

### Run a scan

The **Search** section takes a search root, typed or chosen with the folder picker, a search mode of
**Fingerprints** or **Embeddings + fingerprints**, and a **Skip spectral** toggle. **Find duplicates** starts the
scan, and the button becomes **Stop** while it runs. Progress shows the current phase and the
processed count. The scan writes the same JSON, XLSX, and log files a CLI run writes, under the same
report directory.

One scan runs at a time, and a second start is refused rather than queued. The dialog exposes no
preset, threshold, source, weight, stored-path filter, or group limit, so a run that needs those
stays a CLI run. Its report still opens here.

### Choose a report and narrow it

The **Report and filters** section lists every report in the report directory, newest first, with
its generation time, root, and group count. The XLSX link downloads that run's workbook.

| Filter | Effect |
| --- | --- |
| Confidence | Keeps groups whose confidence is high, medium, or manual review |
| Fingerprint at least | Keeps groups whose best exact fingerprint score reaches this value |
| Transcodes only | Keeps groups holding at least one suspected transcode |
| Path contains | Keeps groups where one stored path contains this text |

Groups load `25` at a time. **Mark candidates** selects the suggested copies in every group on the current
page, and **Clear all** drops the whole selection. A selection survives paging and filter changes.

### Read a group

Each group card carries its group number, a confidence chip, the best exact fingerprint score in the
group, the number of copies, and a transcode count when the spectral check flagged one.

Every copy in the group gets a card, the suggested keeper included. A card shows:

- a play button that streams `/media/{track_id}` through the app's single player, disabled when the
  file cannot be read;
- the file name, the stored artist and title when present, and the full stored path;
- a badge naming the suggested keeper or a duplicate copy;
- format, resolution, size, and duration on one strip, then the spectral verdict, then the
  remaining facts. A lossless copy leads with sample rate and bit depth, and its bitrate trails as
  "stream". Lossless compression packs the same samples into fewer bits, so a FLAC and the WAV it
  came from differ in bitrate while carrying identical audio, and leading with that number reads as
  if the FLAC were the worse copy. A lossy copy leads with its bitrate instead, because there the
  number is the quality signal;
- one verdict line for a duplicate copy, naming the evidence it rests on. A safe candidate reads
  that MERT and MAEST corroborated the match. Otherwise the line states the exact fingerprint score
  and that one fingerprint is not enough to delete automatically, and a score under `0.9` adds that
  a partial match is what a vinyl rip against a digital copy, or a remaster, looks like. The
  suggested keeper carries no verdict line because its badge already states the role.

Each card then lists the report's own sentences under **Details**, deduplicated: the report states
each fact twice, once as `Manual review required: X.` and once as `X`, and the prefix and trailing
period are stripped before matching. In fingerprint mode the sentences that only report an unloaded
embedding, such as "MERT source disabled" or "missing content similarity", are dropped rather than
listed. No embedding is loaded in that mode by design, so those lines describe the run rather than
the pair, and reading them as findings about the two copies is misleading.

The listed sentences are translated for the screen; a sentence with no translation is shown in the
report's own wording rather than hidden. The JSON, XLSX and log artifacts stay English, because they
are the record the CLI writes and reads.

Every listed file is rechecked against the current database and the disk with the tests the deletion
gate runs later. A file that no longer matches its report row is marked stale with a reason, so a
stale candidate is visible before confirmation instead of appearing in the skipped list afterwards.
The reasons are a track that left the library, a stale report identity, missing or stale reported
file facts, and a file missing on disk.

### Confirm a deletion

**Mark everything except the suggested keeper** in one group marks every duplicate that is not stale
and leaves the suggested keeper. Any copy can be marked instead, the keeper included, and **Delete
this copy** toggles a single card. A group with every copy marked shows a warning, and the dialog
blocks the request while that group is on the page. The server applies the same rule to the whole
selection by skipping those copies.

The footer counts the marked copies and the groups they came from. Its size total covers the marked
copies on the current page, so it understates a selection spread over several pages.

The footer holds a **Destination** select with **To the recycle bin** and **Permanently**, then the
**Delete the marked copies** button. That button is enabled as soon as one copy is marked and no
request is in flight. There is no phrase field in the browser.

Pressing it opens a **Yes** / **No** confirmation naming the copy count, the group count, and the
total size. Answering **Yes** sends the request. See [Deleting duplicates](#deleting-duplicates) for
the gates the request then passes.

## Sources and weights

`--embedding` mode enables all four embedding sources by default:

| Source | Raw weight |
| --- | ---: |
| MERT | 0.43 |
| MAEST | 0.32 |
| MuQ | 0.12 |
| CLAP | 0.04 |

Raw weights are configuration coefficients, not percentages. The scorer divides by the total weight of the enabled evidence that is available for a pair. The duplicate score can also include stored SONARA and duration evidence.

In `--embedding` mode the CLI accepts repeatable `--source` and `--weight FAMILY=VALUE` options.

Validation is fail-closed:

- `--source` and `--weight` require `--embedding`.
- `sources` must be nonempty, unique, and limited to the four supported families.
- When `weights` is supplied, its keys must exactly match the enabled sources.
- Every weight must be finite and nonnegative, and at least one must be positive.

## Candidate retrieval and fingerprint review

In `--embedding` mode, candidate construction takes a set union rather than applying one signal
after another. Fingerprint mode instead retrieves from fingerprint LSH alone.

| Signal | Candidate-retrieval role |
| --- | --- |
| MERT/MAEST LSH | Used in `--embedding` mode for suitable high-dimensional embeddings. |
| Duration window | Used in `--embedding` mode when embedding LSH produces no candidate pairs. |
| SONARA fingerprint LSH | Uses compact descriptors from valid stored fingerprints. A pair must share one 24-bit key made from two adjacent 12-bit bands. Comparisons stay inside one fingerprint version. |

The native SONARA matcher then verifies pairs retrieved by either fingerprint LSH or MERT/MAEST
LSH. Pairs found only by the duration window do not trigger native fingerprint matching. This
keeps the expensive comparison out of the broad duration fallback. The 24-bit fingerprint key
also filters accidental LSH collisions before native verification, while either LSH signal can
still contribute fingerprint evidence.

An exact native fingerprint score of at least `0.45` can create a **manual-review** candidate,
even when embeddings or duration data are absent. A pair retrieved only by `fingerprint_lsh`
never becomes an automatic delete candidate: it carries an explicit manual-review blocker. The
normal MERT/MAEST, content-similarity, duration, identity, and confirmation requirements for
safe deletion remain in force.

The order in which the two independent LSH paths are scheduled changes latency only, not their
union of candidate pairs. A synthetic comparison is available for recall and cost checks:

```powershell
python tools\audio-dedup\benchmark_fingerprint_candidates.py --groups 32 --distractors 128
```

It uses known synthetic duplicate groups, reports retrieval recall, candidate-pair counts, and
timing for fingerprint LSH, embedding LSH, and their union. It does not estimate precision on a
real music library. Run Audio Dedup in report-only mode and listen to the fingerprint-review pairs
before changing the review threshold.

To disable MuQ and reproduce the exact legacy source profile, select only MERT, MAEST, and CLAP. Omitting explicit weights gives those sources their legacy raw weights:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music `
  --embedding --source mert --source maest --source clap
```

This exact profile uses MERT 0.43, MAEST 0.32, and CLAP 0.04. Any other source or weight configuration uses the non-legacy deletion-safety rules below.

## Spectral transcode check

In both search modes, the report step decodes every file that belongs to a duplicate group (only
those files, not the whole scope) and estimates its spectral cutoff. The read-only FFmpeg decode
covers three `24`-second windows centered at `15`%, `50`%, and `80`% of the track (short files
use a single window), first audio stream, mono, `f32` samples. Each window averages its loud
frames in linear power; the cutoff is the highest frequency still within `50` dB of the median of
the `1` to `8` kHz reference band. The window with the widest cutoff decides the file, so one
full-band window clears a copy while a true transcode stays walled in every window. The analysis
uses the stored `tracks.sample_rate_hz` value.

A lossless container whose widest window ends in a brickwall below `19.45` kHz, dropping at least
`14` dB across the cutoff, is marked `suspected_transcode`. The ceiling sits below the wall a 320 kbps
encoder leaves, near `20.1` kHz, so that class is a known miss rather than an oversight: raising the
ceiling and gating it on a steeper drop was measured against the project's 1000-file reference and
added three false alarms for no extra detection, because honest masters in this library also carry
steep walls near 20 kHz. That is fake-bitrate evidence, such
as an MP3-sourced rip stored as FLAC or WAV. A lossy container is instead measured against the
stored `tracks.bit_rate_bps` value and becomes suspect only when its wall sits below the cutoff
expected at that declared bitrate. The note then records a match or a shortfall. A gradual
roll-off is not a brickwall, so dark masters stay clean. Files that keep energy above `21` kHz
get a `full band` note; lower cutoffs are noted as a brickwall with an estimated bitrate class or
as a roll-off near the cutoff. Every verdict is evidence for review, never an automatic deletion
decision.

Keeper choice prefers copies that are not suspected transcodes ahead of every other ranking key:
format rank, size-per-second, metadata completeness, and modification time. So a full-band WAV
outranks a suspected-transcode FLAC. When even the chosen keeper is suspected, the
group gains the blocked reason `every remaining copy is a suspected transcode; verify spectra by
ear`.

Unreachable files, decode failures, and unknown sample rates are skipped with an explicit
per-file note, never guessed. When `ffmpeg` is not on `PATH`, the whole check is skipped with the
note `ffmpeg unavailable`. `--skip-spectral` disables the check.

The per-file verdict also rolls up to group and report level: `report_statistics` counts
`fake_bitrate_candidate_count` (duplicate candidates, not keepers, that are suspected transcodes)
and `fake_bitrate_group_count` (distinct groups containing at least one of them). The XLSX Groups
sheet exposes a `fake_bitrate_candidates` count per group and highlights any row where it is above
zero in amber, separate from the sheet's existing green safe-delete and red review-manually
highlighting, so transcoded duplicates stand out as deletion candidates at a glance.

## CLI report mode

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db .\data\library.sqlite --root D:\Music --preset safe
```

Omitting `--db` selects `database\volumes.sqlite` under the repository root, the same default the
launcher suggests.

The CLI updates one console line while it runs. It loads track records and only
the embedding families the selected mode needs in SQLite chunks of 200 tracks, showing the
phase, percentage, and processed items as `N/M`. During pair scoring, `N/M`
refers to candidate pairs.

## Command examples

The two mode flags are mutually exclusive. `--source` and `--weight` require `--embedding` and
fail otherwise. Every run is report-only unless `--apply` is passed. `--root` accepts any
stored-path prefix, including a bare drive root such as `D:/`.

Default fingerprint report over one volume, with the default database:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --root M:/Volumes
```

The same run with the search mode spelled out:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --fingerprint --root M:/Volumes
```

Narrow the scope to one subfolder plus repeatable stored-path substrings:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --root M:/Volumes/Techno --path-contains vinyl --path-contains 2019
```

Select another database and another report directory:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --db C:/db/library.sqlite --root D:/Music --out-dir C:/reports/audio-dedup
```

Write at most `50` duplicate groups:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --root M:/Volumes --limit-groups 50
```

Fast run without the FFmpeg spectral check:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --root M:/Volumes --skip-spectral
```

Embedding mode with the default four families and weights:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --embedding --root M:/Volumes
```

Embedding mode over an explicit family subset, where the weights must cover exactly the enabled
sources:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --embedding --root M:/Volumes `
  --source mert --source maest --weight mert=0.6 --weight maest=0.4
```

Embedding mode with the balanced preset and explicit threshold overrides:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --embedding --root M:/Volumes `
  --preset balanced --min-score 0.94 --min-similarity 0.96
```

Destructive apply run. It writes reports first and then prompts for the exact phrase
`APPLY DELETE`. Only safe delete candidates are deleted, and those exist only in embedding mode:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --embedding --root M:/Volumes --apply
```

Full flag reference:

```powershell
python tools\audio-dedup\audio_dedup_cli.py --help
```

## Safe-delete corroboration

Safe delete candidates exist only in `--embedding` mode. The flag is what lets `--apply` act without
per-copy review. A reviewer can still confirm a deletion from any report in the browser, including a
fingerprint-mode report that carries no safe candidate at all.

MuQ and CLAP can affect ranking and report candidates, but they cannot replace MERT plus MAEST evidence for automatic deletion.

The exact legacy profile keeps its previous aggregate gate. Every non-legacy source or weight configuration requires:

- current MERT and MAEST evidence for the pair;
- a positive MERT weight and a positive MAEST weight;
- an independent MERT-plus-MAEST weighted similarity that meets the preset `min_similarity`;
- the existing duration compatibility gate.

A high MuQ or CLAP similarity by itself can produce a review candidate, but never a safe delete candidate.

## Deleting duplicates

Deletion is destructive in both surfaces, and the delete endpoint requires the exact phrase
`APPLY DELETE` in its request body. Who supplies that phrase differs.

From the CLI, `--apply` prints a `DESTRUCTIVE APPLY REQUESTED` block naming the database, the root,
and the candidate count, then waits for the operator to type the phrase. Anything else cancels.

From the browser, the client inserts the phrase itself and the reviewer answers a **Yes** / **No**
dialog. Nobody types `APPLY DELETE` in the browser. The phrase stops a stray POST from deleting
audio rather than gating the person at the screen.

Every deletion runs the same per-file gates. A target must sit inside the run's root. The tool then
rechecks the report identity fields `catalog_uuid` and `track_uuid`, the stored path, and the
reported `size` and `file_modified_ns` against the live database, and confirms that the file is
still on disk. A target that fails one of those checks is skipped with its reason while the rest of
the run continues.

SQLite rows are removed only for tracks whose files were deleted. Removing a track row also clears
that track's rows in the optional Evaluation database, because the sidecar is a separate file that
no foreign key reaches. After the deletions, matching rows are also removed from the Rhythm Lab
labels database. A SQLite failure in that cleanup does not abort the run: it is recorded in the
result's `failed` list as `rhythm_lab_cleanup:` plus the error.

### What each surface deletes

| Surface | Targets | Copy that must survive |
| --- | --- | --- |
| CLI `--apply` | Safe delete candidates in the report | The group's suggested keeper, which must still exist on disk |
| Browser review | The copies you marked, the keeper included | Any group member left unmarked, which must still exist on disk |

The CLI path skips a candidate whose keeper is gone with the reason `keeper file is missing on disk`.
The browser path skips every marked copy of a group that would lose all of its copies, with the
reason `group would lose every copy`. Safe candidates exist only in `--embedding` mode, so `--apply`
finds nothing to delete in a fingerprint-mode report and the browser review is that report's
deletion path.

A browser deletion takes its root from the report payload, so a deletion covers the scope of the
scan it reviews. A report written against another database is refused before any file is touched,
and the deletion holds the database exclusively while it runs.

### Recycle bin or permanent

The browser review offers **To the recycle bin** and **Permanently**, and starts on the recycle
bin. Recycle bin deletion uses the `send2trash` package, a project dependency. It never falls back
to a permanent delete. A missing package fails the request before any file is touched. A
recycle-bin failure on one file leaves that file in place and records the error in the result's
`failed` list. The CLI `--apply` run deletes permanently.

### After a deletion

A confirmed CLI apply rewrites the JSON, XLSX, and log reports, so every saved report describes the
apply run. The XLSX Summary sheet's `Mode` row then reads `apply` instead of `report-only`.

A browser deletion leaves the report files untouched. The report stays the record of the scan that
produced it, and the deleted copies appear as stale on the next page load. The response carries the
deleted track ids and paths, the skipped and failed entries, and the Rhythm Lab row count.

Do not run either deletion path during routine tests. Review the report first and keep backups when
the library matters.

## Output

Reports default under `tools/audio-dedup/data/reports/` and include JSON, XLSX, and log output. The JSON payload records `search_mode`, `sources`, `weights`, and `fingerprint_retrieval` metrics: validated and rejected stored fingerprints, LSH/exact candidate counts, the review-pair count, and the threshold. Pair evidence records `fingerprint_similarity` and `candidate_sources`; the XLSX Pair Evidence sheet exposes the same provenance, while its Summary sheet lists the search mode, valid fingerprints, and fingerprint-review pairs. The Summary sheet's "Embeddings loaded (this run)" block counts the vectors loaded for this run's scoring, so every family reads `0` in fingerprint mode. The text log carries a matching `search_mode=` line. Safety failures appear in `blocked_reasons`.

Spectral evidence has its own surfaces. Track rows carry `spectral_cutoff_hz`, `spectral_sharpness_db`, `suspected_transcode`, and `spectral_note`. Candidate rows repeat the cutoff, flag, and note, and the keeper and candidate explanations state when a spectrum looks transcoded. A top-level `spectral_analysis` block counts checked, analyzed, skipped, and suspected files. The `statistics` block also carries `fake_bitrate_candidate_count` and `fake_bitrate_group_count`, the duplicate-candidate roll-up described in the spectral transcode check above. The XLSX Candidates sheet adds `suspected_transcode`, `spectral_note`, `keeper_suspected_transcode`, and `keeper_spectral_note` columns, and highlights a `true` `suspected_transcode`/`keeper_suspected_transcode` cell in amber. The Groups sheet adds a `fake_bitrate_candidates` column and highlights the whole row in amber when it is above zero. The Summary sheet adds "Suspected transcodes in groups", "Fake-bitrate duplicate candidates", and "Spectral checks" rows, and the text log carries a `suspected_transcodes=` line.

Reports are local private artifacts.
