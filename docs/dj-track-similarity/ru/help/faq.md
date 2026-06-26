# FAQ

Аудитория: new and returning users  
Цель: short conceptual answers  
Тип: explanation

## Does the app upload my music?

No. Documented workflows are local. Audio analysis reads local files and writes
local SQLite state.

## Does scan rewrite audio tags?

No. Scan reads selected metadata into SQLite. Standard-genre write workflow is a
separate explicit action.

## Why several analysis families?

They answer different questions. SONARA is feature-oriented, MERT is audio seed
similarity, CLAP supports text prompts, MAEST contributes embeddings and genre
analysis, and classifiers represent concepts you train.

## Can SET make a finished DJ set?

No. SET makes ranked and ordered preview. Listen, adjust and export only after
review.

## Why are some tracks missing from SET?

SET requires feature-complete candidates: SONARA, MERT, MAEST and CLAP audio
embeddings.

## Can I use this as a research benchmark?

No. It is a practical local utility and personal project, not a formal
benchmark.
