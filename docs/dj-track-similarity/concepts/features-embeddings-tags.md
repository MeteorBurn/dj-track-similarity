# Features, embeddings, and tags

Audience: users comparing analysis families  
Goal: separate the project data types clearly  
Type: explanation

The app stores several kinds of information. They look similar in the UI, but
they are not interchangeable.

## File tags

Tags come from the audio file metadata: title, artist, album, BPM, key, and
other human-facing fields. Scan and RefreshTags read a fixed practical
whitelist into SQLite.

For Smart Set Builder, tag BPM is preferred when present. SONARA BPM is a
fallback.

## SONARA features

SONARA writes feature values, model metadata, and derived working fields such as
BPM, key, duration, and energy into SQLite. These are analyzed values, not file
tags copied back to audio.

## Embeddings

MERT, CLAP, and MAEST store vector embeddings in SQLite. Search and SET can use
these vectors as similarity signals.

MAEST also produces genre analysis, but SET selection should not rely on MAEST
genre labels. MAEST embeddings are a different signal.

## Classifier scores

Promoted classifier profiles write scores to `track_classifier_scores`. A score
belongs to one classifier key. Missing classifier scores are neutral for SET.

## Reports and exports

Reports, playlists, and helper-tool output are local files. They are not the
same thing as library state and can usually be regenerated.
