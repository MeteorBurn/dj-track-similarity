# Обучить личный classifier

> Audience: Пользователи, которым нужны собственные taste signals в основном приложении.
> Goal: Разметить в Rhythm Lab, обучить, promote и безопасно посчитать scores.
> Type: how-to

Personal classifier полезен, когда вкус трудно выразить одним prompt или feature slider: например, "живые барабаны" или "избегать фестивального вокала". Ожидайте итерацию: разметить понятную идею, обучить, послушать ошибки, добавить labels и обучить снова.

## Поток

- Запустите Rhythm Lab из основного UI или CLI.
- Выберите binary или multiclass profile.
- Добавьте достаточно labels для активного profile.
- Запустите training; calibration опциональна и требует достаточно данных.
- Выполните promote модели в `models/classifiers/<artifact-prefix>/`.
- Посчитайте scores этого classifier во вкладке CLASS основного приложения.

## Binary или multiclass

- Binary profile подходит для одного positive idea и одного negative counterexample. Это самый простой старт для yes/no сигнала.
- Multiclass profile подходит, когда трек должен принадлежать одному из нескольких пользовательских классов. В активном multiclass profile у трека может быть только один текущий class label.

## Что означает каждый этап

- Labeling пишет состояние Rhythm Lab под `tools/rhythm-lab/data/`; source audio не меняется.
- Training читает существующие SONARA, MERT и MAEST inputs и пишет artifacts под `tools/rhythm-lab/artifacts/<artifact-prefix>/`.
- Promotion копирует выбранную модель в `models/classifiers/<artifact-prefix>/`, где её видит основное приложение.
- Scoring пишет probabilities в `track_classifier_scores` SQLite. Scores scoped by `classifier_key`, поэтому scoring одного classifier не должен стирать scores другого.

Первую модель воспринимайте как rough filter. Результаты во вкладке CLASS — это suggestions for listening, а не автоматическое решение.
