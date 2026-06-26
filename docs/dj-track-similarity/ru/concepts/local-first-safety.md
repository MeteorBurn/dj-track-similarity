# Local-first safety

Аудитория: все пользователи  
Цель: показать, что может изменять каждый workflow  
Тип: explanation

Проект построен вокруг local files и explicit write boundaries. App не
загружает ваше аудио наружу.

## Normal read-only audio workflows

Эти workflows могут читать audio files и писать SQLite state, но не
переписывают source audio:

- scanning tags into the library database;
- refreshing tag metadata;
- SONARA, MAEST, MERT, CLAP and classifier analysis;
- browsing and preview playback;
- seed search, text search, SONARA search and SET previews;
- reset and clear actions for database analysis state;
- playlist/report export.

Browser preview может транскодировать AIFF/AIF в WAV для streaming. Это
read-only media response, не rewrite source file.

## What writes SQLite

Main app хранит library rows, metadata, analysis results, embeddings, search
state, likes и classifier scores в SQLite. Writes идут через database layer с
path-scoped lock.

## What writes reports

Exports, duplicate reports и audio repair reports пишут local files в selected
output directory. Reports отделены от source audio.

## What can write audio tags

Explicit standard-genre write workflow может писать stored MAEST genre labels в
standard audio genre tags. Это не часть normal analysis или search.

## What can delete audio

Только duplicate cleanup apply mode предназначен для удаления audio files, и
только после explicit apply workflow and confirmation. Routine verification and
tests не должны запускать destructive apply mode.
