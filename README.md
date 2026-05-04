# dj-track-similarity

Локальная утилита для подбора похожих треков под монотонные seamless DJ-сеты.

## Запуск

```powershell
dj-sim serve --host 127.0.0.1 --port 8765
```

Открой:

```text
http://127.0.0.1:8765/
```

В этом workspace также есть быстрый Windows-скрипт:

```powershell
scripts\run_server.cmd
```

## CLI

```powershell
dj-sim scan "D:\Music"
dj-sim analyze
dj-sim analyze --device cpu --batch-size 2
dj-sim analyze --device cuda --batch-size 8
dj-sim analyze --fake
dj-sim export 1 --format m3u --output-dir "D:\Exports"
dj-sim export 1 --format csv --output-dir "D:\Exports"
dj-sim tag-preview 1 2 3
dj-sim tag-apply 1 2 3
```

`analyze` использует `m-a-p/MERT-v1-95M` через PyTorch/Hugging Face и может скачать веса при первом запуске. `--fake` нужен только для smoke-тестов без ML.

В UI `Analyze limit` по умолчанию равен `0`, то есть анализируется вся
библиотека. Если нужен короткий тест, укажи нужное целое число треков вручную.

## Analysis performance

MERT-анализ ускоряется не Python-многопоточностью, а выбранным устройством и
размером inference batch.

- `auto` выбирает CUDA, если PyTorch видит GPU, иначе использует CPU.
- `cpu` стабильнее и подходит для проверки совместимости, но обычно медленнее.
  Начинай с `batch size 1-4`.
- `cuda` обычно быстрее. Начинай с `batch size 4-8`; если нет ошибок памяти,
  можно повышать осторожно.
- `batch size` влияет на скорость и потребление памяти, но не должен менять
  результат эмбеддингов, потому что mixed precision сейчас не включен.
- Если CUDA запрошена, но недоступна, анализ завершится ошибкой вместо тихого
  fallback на CPU. Для fallback используй `auto`.
- `Fake smoke` / `dj-sim analyze --fake` проверяет pipeline без загрузки MERT.
- В UI у параметров есть hover-подсказки с назначением, форматом, типом и
  диапазоном значений.

## Safety

- Аудиофайлы не меняются при сканировании, анализе, поиске и экспорте.
- `tag-preview` ничего не пишет.
- `tag-apply` пишет только custom tags `DJ_SIM_*` и не перезаписывает стандартные BPM/key/mood.

## Current MERT validation mode

Текущая основная задача проекта - проверить, насколько `m-a-p/MERT-v1-95M`
полезен для поиска похожих треков сам по себе.

В UI сейчас активны только параметры, которые напрямую относятся к этой
проверке:

- `Similarity` - минимальный raw cosine score. По умолчанию `0`, чтобы не
  отрезать кандидатов до накопления реальной статистики по библиотеке.
- `Lookback` - добавляет последние N треков текущего сета в centroid-контекст.
- `Limit` - ограничивает количество результатов.

Отключенные параметры не отправляются в поиск из UI:

- `BPM` и `Key` отключены, чтобы не смешивать MERT similarity с фильтрацией по
  метаданным во время базовой проверки модели.
- `Energy` отключен, потому что проект пока не вычисляет реальную энергию
  трека.
- `Epsilon` отключен до калибровки на реальных MERT score: без статистики он
  может случайно выкинуть хорошие кандидаты.
- `Noise` отключен до безопасной калибровки: текущая рандомизация может
  перебить реальную разницу similarity score.

## Future features

Будущие направления в моем порядке ожидаемой пользы для проекта:

1. `Search calibration` - проверить распределение MERT cosine score на реальной
   библиотеке и подобрать рабочие значения `Similarity`, `Epsilon` и безопасной
   рандомизации. Это важнее новых моделей, потому что сначала нужно понять,
   насколько текущий MERT-слой стабилен и полезен на реальных 4000+ треках.
2. `Auto chain` - автоматическая сборка очереди похожих треков с постепенным
   дрейфом сета. Текущий `Lookback` только добавляет последние N треков сета в
   общий centroid-контекст поиска. `Auto chain` должен работать иначе: взять
   seed, найти несколько ближайших кандидатов, добавить их в очередь, затем
   использовать последний трек или последние N треков как новый контекст и
   повторять шаги до достижения `Limit`. Возможные параметры: `Step size`,
   `Chain context`, `Similarity floor`.
3. `Mel/CNN similarity` - поиск по mel-спектрограммам через CNN/аудио-визуальные
   embeddings. Цель: ловить паттерн, структуру, грув, плотность и спектральный
   рисунок треков. Это хороший второй audio-to-audio слой рядом с MERT.
4. `Music feature similarity` - отдельный explainable DSP-слой из набора
   признаков: FFT, MFCC, PLP, Mel Spectrogram, Constant-Q Transform, Chroma
   Features, Spectral Centroid, Spectral Rolloff, Spectral Bandwidth, Spectral
   Flatness, Zero Crossing Rate, RMSE, Waveform Envelope, Autocorrelation.
   Цель: получить дополнительный score похожести и объяснять, почему треки
   похожи или отличаются.
5. `CLAP / LAION-CLAP` - текстово-аудио поиск по описанию вайба. Цель: искать
   треки запросами вроде `dark hypnotic techno`, `warm melodic house`, `no
   vocals`, а затем совмещать результат с MERT/audio similarity. Это мощный
   слой, но он решает уже семантический поиск, а не базовую audio-to-audio
   похожесть.
6. `DJ transition features` - beatgrid, downbeat, phrase structure, loudness,
   real energy, spectral balance по интро/аутро, вокальность,
   groove/percussion density и другие признаки, важные именно для качества
   сведения. Это отдельная задача на усовершенствование после проверки базовых
   similarity-подходов.
7. `MERT model upgrade` - добавить опциональную модель `m-a-p/MERT-v1-330M`
   после проверки стабильности текущего pipeline на `m-a-p/MERT-v1-95M`.
8. `Scale improvements` - рассмотреть ANN-индекс или кэш матрицы эмбеддингов
   для больших библиотек.

## Search knobs

- `Similarity` задает минимальный raw cosine score.
- `Lookback` добавляет последние N треков текущего сета в centroid-контекст поиска.
- `Epsilon` и `Noise` есть в backend как экспериментальные ручки, но в UI
  отключены до калибровки.
