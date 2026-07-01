# Analysis families reference

> Audience: Users choosing analysis data to run.
> Goal: Map each family to output and UI use.
> Type: reference

## Families

| Family | Output | Used by | Audio writes? |
| --- | --- | --- | --- |
| SONARA | features and derived working BPM/key/duration/energy | SONARA search, SET routing | No |
| MAEST | embeddings and genre metadata | SET inputs, genre display/tag apply source | No during analysis |
| MERT | audio embeddings | MERT seed search, SET inputs | No |
| CLAP | audio embeddings; text query embeddings at search time | CLAP text search, SET inputs | No |
| CLASSIFIERS | `track_classifier_scores` | CLASS tab, optional SET modifiers | No |

## Command

```powershell
dj-sim analyze --models sonara,maest,mert,clap --db <library-db>
```
