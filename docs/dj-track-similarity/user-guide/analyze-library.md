# Analyze the library

Audience: UI users  
Goal: run analysis jobs from the browser UI  
Type: how-to

Analysis jobs fill the local SQLite database with features, embeddings, labels,
or classifier scores. Choose the smallest useful job for the workflow you want.

## Controls

The Library panel exposes model checkboxes and job controls for:

- SONARA;
- MAEST;
- MERT;
- CLAP;
- CLASSIFIERS, when promoted classifier models exist.

Important settings:

- `Analyze limit`: `0` means the whole missing set for selected families.
- `Device`: `AUTO`, `CPU`, or `CUDA`.
- `Track batch size`: number of decoded tracks handled together.
- `Inference batch size`: MAEST/MERT/CLAP model forward-pass batch size.

## Recommended order

1. Run SONARA on a small limit to unlock feature-based browsing and seed search.
2. Run MERT when you want seed-track audio similarity.
3. Run CLAP when you want text search.
4. Run MAEST when you want genre labels, syncopated-rhythm filtering, or
   classifier inputs.
5. Run CLASSIFIERS after promoting models from Rhythm Lab.

## Reset behavior

Analysis reset controls remove database records for the selected family. They
do not rewrite source audio files.

Classifier reset is scoped to stored classifier scores in SQLite. Recompute a
classifier after retraining and promoting a new model for the same
`classifier_key`.
