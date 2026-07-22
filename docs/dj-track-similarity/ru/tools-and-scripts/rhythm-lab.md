# Rhythm Lab

> Для кого: Пользователи, создающие локальные профили классификаторов.
> Задача: Размечать, обучать, публиковать и передавать коллекции, не смешивая исходные базы.
> Тип: Руководство

Rhythm Lab — отдельное приложение для разметки и обучения. Основной интерфейс умеет запускать его,
а панель поиска — сохранять текущий сет как коллекцию Rhythm Lab.

В новой базе меток нет встроенного профиля. Создайте его в интерфейсе или передайте нужный
`--profile` командам CLI, которые работают с конкретным профилем.

## Запустите интерфейс

В основном приложении нажмите значок колбы. Серверная часть запустит или повторно использует Rhythm Lab на
порту `8777`.

Ручной запуск:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py serve --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Откройте:

```text
http://127.0.0.1:8777/
```

## Основные команды CLI

Обучение:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py train --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Предсказание:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py predict tools\rhythm-lab\artifacts\live_instrumentation\combined\model.joblib --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Публикация:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Отчёт калибровки:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py calibration-report --profile live_instrumentation --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Калиброванное обучение включается явно и не показано во вкладке Training:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py train --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite --calibrate
```

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py benchmark-ablation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite --profile live_instrumentation --calibrate-finalists --output tools\rhythm-lab\artifacts\ablation-calibrated.json
```

Для намеренной публикации калиброванного артефакта потребуйте калибровку:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation --feature-set 'mert+maest' --require-calibration --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

Предложение меток:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py suggest-labels --profile live_instrumentation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite --limit 25
```

## Коллекции

Основной интерфейс умеет сохранить текущий сет как коллекцию Rhythm Lab. Создать или обновить
коллекцию можно и из CLI:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py collection-save --labels tools\rhythm-lab\data\rhythm_lab.sqlite --name "review pile" --track-id 123 --track-id 456
```

Список коллекций:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py collection-list --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

## Понравившиеся треки

В строке трека есть кнопка с сердцем для общего состояния «нравится». Счётчик Liked в полосе
Coverage открывает понравившиеся треки текущей исходной базы. Операция изменяет только таблицу
`track_likes` основной библиотеки SQLite и не записывает аудиофайлы или теги.

## Очередь активного обучения

Команды `queue`, `queue-export`, `queue-mark` и `queue-clear` позволяют показывать, экспортировать,
помечать и очищать строки очереди. Они всегда ограничены профилем и требуют `--profile`.

## Удаление профиля

Удаление профиля явное и защищено подтверждением. Кнопка `Delete` в интерфейсе просит ввести имя или
ключ профиля. После подтверждения удаляются метки, предсказания, строки очереди, контрольные точки
обучения, метрики и локальные обучающие артефакты этого профиля. Опубликованные модели основного приложения в
`models/classifiers/` не удаляются.

CLI использует то же точное подтверждение:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py delete-profile --profile live_instrumentation --confirm live_instrumentation --labels tools\rhythm-lab\data\rhythm_lab.sqlite
```

## Абляционные сравнения

Запустите сравнительный тест, если нужны локальные данные о вариантах источников признаков одного
профиля:

```powershell
python tools\rhythm-lab\rhythm_lab_cli.py benchmark-ablation --source .\data\library.sqlite --labels tools\rhythm-lab\data\rhythm_lab.sqlite --profile live_instrumentation --output tools\rhythm-lab\artifacts\ablation.json
```

Команда читает исходную библиотеку без записи. Экспериментальные артефакты остаются в каталоге
профиля, а результат сохраняется как JSON. Модели не публикуются, оценки классификаторов не
записываются.

Матрица абляций по умолчанию включает сочетания только эмбеддингов, исходный набор признаков
плейлиста SONARA и два варианта SONARA 2.0:

- `sonara2` добавляет числовые необязательные поля SONARA 2.0: сводки структуры, громкости, сетки
  долей и тишины, но исключает `vocalness`, четыре показателя `mood_*` и `instrumentalness`;
- `sonara2vocal` использует те же поля и добавляет `vocalness`.

Во время расчёта обоим вариантам нужны только сохранённые признаки SONARA. Сравнивайте их отдельно
для каждого профиля до публикации: польза `vocalness` зависит от смысла меток конкретного профиля.

Обучение, зависящее от SONARA, принимает лишь треки с одной общей актуальной сигнатурой анализа.
Обучающие артефакты и опубликованный манифест версии `2` сохраняют эту сигнатуру. Предсказание,
публикация и расчёт в основном приложении отклоняют отсутствующую или несовпадающую сигнатуру,
поэтому модель на старой семантике danceability, acousticness или vocalness не сможет незаметно
оценить актуальные строки Core схемы v6. Отсутствующее обязательное поле — несовместимые данные, а
не числовой ноль. Наборы признаков, состоящие только из эмбеддингов, не требуют сигнатуры SONARA.

После изменения ревизии признаков переобучите и опубликуйте затронутые профили. Открытие основной
библиотеки делает зависимые оценки классификаторов недействительными; открытие базы Rhythm Lab
делает недействительными зависимые предсказания. Предсказания только по эмбеддингам, исходные метки
и обратная связь сохраняются. Сброс SONARA удаляет зависимые оценки основной библиотеки, но не метки
Rhythm Lab. Старые опубликованные файлы модели остаются на диске для восстановления, но
блокируются, пока их не заменит актуальный подписанный артефакт.

Mood и instrumentalness остаются в библиотеке для изучения и будущих экспериментов. Сейчас они не
входят в матрицы классификаторов. Полные позиции ритмических долей и атак, метки и события аккордов, кривые
темпа, энергии и громкости, массивы сильных долей, а также эмбеддинг и отпечаток SONARA хранятся
отдельно и никогда не загружаются как признаки классификатора.

Вкладка Training использует тот же процесс активного профиля: собрать метки, обучить, проверить
кандидатов, выполнить сравнение, выбрать вариант и опубликовать. `Train` переобучает по текущим
меткам и автоматически обновляет кандидатов. Калибровка пока скрыта. Публикация из интерфейса
использует некалиброванные артефакты и игнорирует калиброванных финалистов. Для осознанной калибровки
используйте API или CLI.

На запущенном сервере Rhythm Lab доступна калибровка API:

```text
POST /api/profiles/{profile_key}/training/calibrate
{"feature_set": "mert+maest"}
```

Если `feature_set` не указан, используется текущий вариант публикации по умолчанию.

## Безопасность

Rhythm Lab не переписывает исходное аудио. Обычные данные находятся в `tools/rhythm-lab/data/` и
`tools/rhythm-lab/artifacts/`. Явная отметка «нравится» меняет состояние основной библиотеки SQLite.
Удаление профиля может удалить строки базы Rhythm Lab и локальные обучающие артефакты только одного
профиля. Опубликованные модели основного приложения находятся в `models/classifiers/`, не удаляются вместе с
профилем и не должны попадать в Git без намеренного изменения этой политики.
