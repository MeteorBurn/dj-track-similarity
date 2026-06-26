# Analysis families

Audience: users and developers  
Goal: define the analysis families and stored outputs  
Type: reference

## SONARA

SONARA stores feature metadata, model information, and derived working fields in
SQLite. It is used by SONARA search and as part of SET feature completeness.

## MAEST

MAEST analysis stores genre-oriented analysis and embeddings. The app can write
stored MAEST genre labels to standard genre tags only through the explicit
tag-writing workflow.

SET may use MAEST embeddings, but should not use MAEST genre labels for track
selection.

## MERT

MERT stores audio embeddings used for seed search and SET similarity.

## CLAP

CLAP stores audio embeddings used for text search and SET similarity.

## Promoted classifiers

Promoted classifier scoring reads existing SONARA features plus MERT and MAEST
embeddings, then writes database-only scores to `track_classifier_scores`.
Scoring does not decode audio or modify audio files.

## Device selection

Analysis commands accept `--device`. `auto` chooses CUDA when PyTorch can see a
GPU, otherwise CPU. Explicit `cuda` should fail clearly when CUDA is not
available.
