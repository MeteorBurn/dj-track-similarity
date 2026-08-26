# Features, embeddings, and tags

The UI shows several kinds of information. They are stored together in SQLite, but they come from
different sources and help with different decisions.

## Start with the question

| Question | Useful evidence | What appears in the app |
| --- | --- | --- |
| What does the file already say about itself? | File tags | Searchable artist, title, album, genre, BPM, key, and other metadata |
| Which tracks share a learned audio neighborhood? | MERT | Seed-search rankings |
| Which tracks align on audible rhythm, sound, dynamics, harmony, or tempo? | SONARA | Feature search and transition evidence |
| Which tracks fit a written sound description? | CLAP | Text-search rankings |
| What genre-like and audio evidence does another model add? | MAEST | Display labels, LAB comparison, Audio Dedup, and classifier input |
| How does another general audio model rank this seed? | MuQ | Seed search, a separate LAB group, Audio Dedup, and classifier input |
| Which audio tracks fit a text-aligned music space? | MuQ-MuLan | Separate seed and text-to-track rankings, and classifier input |
| How strongly does a track match my own labeled idea? | Classifier score | CLASS filters |

An embedding is a compact model representation used for comparison. You do not need to interpret
its individual numbers. Features have direct names and can often explain which audible quality
affected a result. File tags are metadata read from the file or written through an explicit tag
workflow.

## File tags

Scan and Refresh Tags use Mutagen to read a fixed metadata set: artist, title, album, genre, year, country, label, catalog number, track number, disc number, BPM, key, comment, ISRC, duration, audio format, and codec data when available.

These are source-file tags. They can be incomplete or inconsistent. The app stores a JSON-safe copy in SQLite.

## SONARA features and embedding

SONARA produces explainable audio features and derived working fields such as BPM, key, duration, and energy. SONARA features support the SONARA tab, Evaluation transition diagnostics, Audio Dedup, and compatible classifier inputs.

Newer SONARA analysis adds optional Camelot key, vocalness, mood, loudness, beat-grid, structure,
and silence fields. Treat these analysis estimates as inspectable evidence. Only fields wired into
a scorer affect ranking.

Mood affinities are shown as analysis data and retained for possible future workflows. They are not
current similarity or classifier inputs. In Custom SONARA search, aggression is an explicit
confidence-aware directional modifier. DJ transition adds a soft structure fit only when the seed
outro and candidate intro data is present. True peak and ReplayGain are also retained
for possible loudness-management features rather than direct SONARA similarity. The current
`sonara` classifier source includes those loudness scalars and vocalness. The existing SONARA
dynamics comparison uses momentary loudness maximum and loudness range; vocalness is also an
explicit search modifier.

SONARA analysis stores compact Core scalars and fixed vectors in `sonara_features`, an unnormalized
48-dimensional `float32` embedding in the dedicated `sonara_embeddings` table, and a versioned
acoustic fingerprint in `sonara_fingerprints`. A successful SONARA pass writes all three rows
together. A fingerprint row contains `track_id`, `track_uuid`, `fingerprint_version`,
`fingerprint_base64`, and `analyzed_at`. Its base64 value is SONARA's native representation.
Timeline collection remains disabled. The stored SONARA embedding and fingerprint are not current
similarity, search, classifier, or Audio Dedup inputs. MAEST, MERT, MuQ, MuQ-MuLan, and CLAP vectors
use their own dedicated tables in the same library database.

SONARA values are analysis results, not copied file tags. Tempo-aware workflows use current
SONARA tempo evidence first. Below `0.45` confidence, they also inspect ranked tempo candidates and
the Mutagen BPM tag. Beat-grid stability can weaken reliability, and unreliable evidence moves
toward a neutral score rather than creating similarity.

The current SONARA `core` output stores `bpm_confidence` beside raw BPM, tempo candidates, and
Camelot key. The confidence value records how strongly SONARA supports its working BPM estimate.

CLI, API, and browser analysis always request the fixed SONARA Core, embedding, and fingerprint
output set. There is no output selector. A normal rerun selects a track when any current row is
missing and writes all three rows together. A track with all three current rows is skipped.

The exact field and scoring boundaries are in the
[SONARA integration reference](../reference/sonara-integration.md).

## MAEST labels and embedding

MAEST stores genre-like labels and a MAEST audio embedding. The labels are used for display and optional standard genre tag writing. LAB Reference Compare and Audio Dedup can use the embedding. Compatible classifier manifests can consume it too.

## MERT embedding

MERT stores an audio embedding. The MERT tab searches from selected seed tracks in this embedding space. LAB Reference Compare, Audio Dedup, and compatible classifier manifests can also use stored MERT embeddings.

## MuQ embedding

MuQ stores a separate audio embedding from 24 kHz `float32` audio. It is tracked as its own analysis family and can be reset independently. The vector supports direct seed search and a separate LAB Reference Compare group. Audio Dedup and compatible Rhythm Lab classifier feature sets can also use it. Audio Dedup can omit `muq` from its explicit source list.

## MuQ-MuLan embedding

MuQ-MuLan uses the official joint music-text model. Its audio analysis reuses the MuQ-compatible
path: mono 24 kHz `float32` audio in 10-second windows. It stores a separate L2-normalized 512D
audio vector in `mulan_embeddings`. Existing MuQ vectors are never converted into this family.

Use the MULAN tab for audio-to-audio seed search. In the TEXT tab, choose
**MuQ-MuLan** to embed text and retrieve only `mulan_embeddings`. Its text and seed scores stay
separate from MuQ and CLAP scores. MuQ-MuLan is available as an explicit Evaluation candidate
source, but it is not added automatically to the default profile or Audio Dedup weights. LAB
Reference Compare includes MuQ-MuLan in its six separate default groups. Rhythm Lab classifier
feature sets that name `mulan` use the stored vector, and the default training recipe
`sonara+mert+maest+clap+muq+mulan` includes it.

## CLAP audio embedding

CLAP analysis stores audio embeddings. The TEXT tab embeds a text prompt at search time and compares it to stored audio embeddings. LAB Reference Compare and Audio Dedup use stored CLAP audio embeddings as audio-to-audio signals, which are not the same as CLAP prompt scores.

## Classifier scores

Promoted Rhythm Lab classifiers write scores under a `classifier_key`. A manifest can require current SONARA, MERT, MAEST, MuQ, MuQ-MuLan, and/or CLAP inputs. Scores are optional and are consumed by the selected CLASS profile.

## Why separation matters

A file genre tag, a MAEST genre label, a CLAP or MuQ-MuLan text score, and an Audio Dedup content
similarity value answer different questions. Use them together, but do not treat them as one shared
scale.
