# Class Tab

> Audience: Пользователи этой страницы.
> Type: how-to

CLASS tab discovers `models/classifiers/*/model.json`. Scoring reads existing SONARA features plus MERT/MAEST embeddings and writes only `track_classifier_scores` scoped by classifier key. After retraining the same key, reset only that key's scores before rescoring.
