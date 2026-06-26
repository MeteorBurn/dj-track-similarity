# FAQ

Audience: new and returning users  
Goal: answer common questions briefly  
Type: explanation

## Does the app upload my music?

No. The documented workflows are local. Audio analysis reads local files and
writes local SQLite state.

## Does scan rewrite audio tags?

No. Scan reads selected metadata into SQLite. The standard-genre write workflow
is a separate explicit action.

## Why do I need several analysis families?

They answer different questions. SONARA is feature-oriented, MERT is audio seed
similarity, CLAP supports text prompts, MAEST contributes embeddings and genre
analysis, and classifiers represent concepts you train.

## Can SET make a finished DJ set?

No. SET makes a ranked and ordered preview. Listen, adjust, and export only
after review.

## Why are some tracks missing from SET?

SET requires feature-complete candidates: SONARA, MERT, MAEST, and CLAP audio
embeddings.

## Can I use this as a research benchmark?

No. It is a practical local utility and personal project, not a formal
benchmark.
