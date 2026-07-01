# Features, embeddings, and tags

> Audience: Readers confused by analysis terms.
> Goal: Separate human tags, measured features, and vector embeddings.
> Type: explanation

## Comparison

| Data | Source | Stored where | Used for |
| --- | --- | --- | --- |
| Mutagen tags | File metadata | `tracks` and metadata JSON | browsing |
| SONARA features | Audio analysis | SQLite metadata/features | SONARA and SET |
| MERT embeddings | Audio model | `embeddings` | seed similarity |
| CLAP embeddings | Audio/text model | `embeddings` | text and audio similarity |
| MAEST data | Genre/model analysis | metadata and embeddings | genre display and SET inputs |
| Classifier scores | Promoted local model | `track_classifier_scores` | CLASS and optional SET modifiers |

## Boundary

Analysis does not rewrite tags. Standard genre tag writing is an explicit separate action.
