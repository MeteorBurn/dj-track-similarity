# Local-first safety

Audience: all users  
Goal: show what each workflow can modify  
Type: explanation

The project is designed around local files and explicit write boundaries. Your
audio is not uploaded by the app.

## Normal read-only audio workflows

These workflows may read audio files and write SQLite state, but they do not
rewrite source audio:

- scanning tags into the library database;
- refreshing tag metadata;
- SONARA, MAEST, MERT, CLAP, and classifier analysis;
- browsing and preview playback;
- seed search, text search, SONARA search, and SET previews;
- reset and clear actions for database analysis state;
- playlist/report export.

Browser preview may transcode AIFF/AIF to WAV for streaming. That is a
read-only media response, not a rewrite of the source file.

## What writes SQLite

The main app stores library rows, metadata, analysis results, embeddings,
search-related state, likes, and classifier scores in SQLite. Writes are routed
through the project database layer with a path-scoped lock.

## What writes reports

Exports, duplicate reports, and audio repair reports write local files under
the selected output directory. Reports are separate from source audio.

## What can write audio tags

The explicit standard-genre write workflow can write stored MAEST genre labels
to standard audio genre tags. It is not part of normal analysis or search.

## What can delete audio

Only duplicate cleanup apply mode is intended to delete audio files, and only
after an explicit apply workflow and confirmation. Routine verification and
tests should not run destructive apply mode.
