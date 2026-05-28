# Семейства анализа

Эта страница документирует analysis outputs, используемые основным
приложением. Используйте ее, чтобы решить, какую analysis job запускать перед
затратой CPU или GPU time. Для отдельного инструмента разметки и обучения
классификаторов см. [Rhythm Lab](rhythm-lab.md).

## Семейства анализа

Каждое семейство пишет разные SQLite data и поддерживает разный workflow:

| Семейство | Что делает | Когда использовать |
| --- | --- | --- |
| Sonara | Извлекает объяснимые playlist features: tempo, energy, loudness, rhythm и tonal summaries. | Нужен быстрый seed search, видимые feature controls или library filters. |
| MAEST | Предсказывает genre labels и сохраняет MAEST embeddings. | Нужны сгенерированные genre tags, review жанров, preset `syncopated` или classifier inputs. |
| MERT | Строит audio embeddings для seed-track similarity. | Нужен сценарий "найти треки рядом с этим треком" через audio model. |
| CLAP | Строит music audio embeddings и text vectors. | Нужен text-to-audio search по описательным prompts. |
| Promoted classifiers | Оценивает треки локальной моделью, обученной в Rhythm Lab. | Нужен переиспользуемый custom signal, например vocal presence, live instrumentation или другой profile-specific label. |

### Sonara

Sonara используется в playlist mode как быстрый explainable feature pass. Она
сохраняет focused playlist features в `metadata_json.sonara_features` и имя
модели в `metadata_json.sonara_model`.

Stored groups and keys:

- Core features: `bpm`, `beats`, `onset_frames`, `onset_density`, `n_beats`,
  `rms_mean`, `rms_max`, `loudness_lufs`, `dynamic_range_db`,
  `spectral_centroid_mean`, `zero_crossing_rate`, `duration_sec`.
- Perceptual features: `energy`, `danceability`, `valence`, `acousticness`.
- Musical key: `key`, `key_confidence`.
- Tonal analysis: `predominant_chord`, `chord_change_rate`, `dissonance`.
- Spectral features: `spectral_bandwidth_mean`, `spectral_rolloff_mean`,
  `spectral_flatness_mean`, `spectral_contrast_mean`, `mfcc_mean`,
  `chroma_mean`.

Sonara BPM и key - анализированные значения, а не копии file tags. Приложение
хранит raw Sonara key data и не выводит Camelot notation.

CLI и UI вызывают Sonara с `batch_size` как parallel track workers, а не как
neural-network inference batch.

Запускайте Sonara рано, если не уверены, с чего начать. Это самое прозрачное
семейство анализа: UI может напрямую показывать и смешивать его feature groups.

### MAEST

MAEST во время анализа пишет genre metadata и embeddings только в SQLite:

- `metadata_json.maest_model`
- `metadata_json.maest_genres`
- `metadata_json.maest_syncopated_rhythm`
- `embeddings.embedding_key = "maest"`

Adapter использует `maest-infer` с `discogs-maest-30s-pw-129e-519l`. Он
анализирует до трех 30-second windows на track:

- offset 60 seconds;
- window около 38 percent duration;
- window около 72 percent duration.

Impossible или duplicate windows clamped and deduplicated. Per-label
activations усредняются по windows, затем top labels сохраняются. MAEST
embedding rows усредняются по тем же windows и сохраняются под embedding key
`maest`.

MAEST analysis сам не изменяет аудиофайлы. Отдельное genre-save action позже
может записать сохраненные MAEST labels в standard audio genre tags.
Флаг `maest_syncopated_rhythm` выводится из сохраненных MAEST genres и
используется library preset `syncopated`.

Запускайте MAEST перед genre writing или preset `syncopated`. Проверяйте labels
перед записью в файлы: analysis database-only, но tag writing - явная мутация
аудиофайлов.

### MERT

MERT строит audio-to-audio embeddings под embedding key `mert`.

Default model:

```text
m-a-p/MERT-v1-95M
```

MERT search использует только MERT vectors. Он не смешивает Sonara features или
CLAP vectors.

Запускайте MERT, когда seed-track similarity важнее explainable controls.
Search results зависят от существующих MERT embeddings, поэтому newly scanned
tracks нужно проанализировать, прежде чем они появятся в полезных MERT results.

### CLAP

CLAP строит music-focused audio embeddings под embedding key `clap` и создает
text vectors для text-to-audio search.

Active checkpoint:

```text
lukewys/laion_clap/music_audioset_epoch_15_esc_90.14.pt
```

Text search требует CLAP audio embeddings, созданных тем же CLAP checkpoint.

Запускайте CLAP, когда нужно искать по mood, instrumentation, energy или другому
описательному языку. Четкие concrete prompts обычно работают лучше, чем
одиночные genre words.

### Promoted classifiers

Promoted classifiers - локальные classifier profiles, а не audio-analysis
models, которые сами декодируют files. Они оценивают tracks из уже сохраненных
analysis outputs:

- SONARA playlist features из `metadata_json.sonara_features`;
- MERT embeddings из `embeddings.embedding_key = "mert"`;
- MAEST embeddings из `embeddings.embedding_key = "maest"`.

Tracks без любого из этих inputs пропускаются classifier job. Scores
сохраняются в `track_classifier_scores` под profile classifier key.

Используйте promoted classifiers после обучения и promotion профиля в Rhythm
Lab. Лучше всего они подходят для персональных concepts библиотеки, которые
трудно описать generic genre label или одним similarity seed.

Стабильные model locations используют profile artifact prefix:

```text
models/classifiers/<artifact-prefix>/model.joblib
```

Эти файлы создаются вне основного приложения командой promotion из Rhythm Lab:

```powershell
.\.venv\Scripts\python.exe tools\rhythm-lab\rhythm_lab_cli.py promote --profile live_instrumentation
```

Promoted `model.joblib` и `model.json` - локальные artifacts, игнорируемые git.
Исходные Rhythm Lab training artifacts остаются в classifier-specific lab
workspace:

```text
tools/rhythm-lab/artifacts/<artifact-prefix>/
```

Promoted metadata генерируется из Rhythm Lab profile и model artifact:
`classifier_key`, profile name, profile type, labels, feature set, source
artifact и training label counts. Rhythm Lab training metrics используют одну
profile-neutral shape для всех profiles (`positive_*` metrics и `label_order`)
вместо classifier-specific metric aliases.

О profile management, labeling, training, prediction, promotion, archive и
delete workflows в Rhythm Lab см. [Rhythm Lab](rhythm-lab.md).

User-facing score - classifier probability для positive training label профиля.
Поскольку UI displays могут округлять probabilities, значение `1.0000` может
быть немного ниже математического `1.0`. Для практической фильтрации
используйте thresholds вроде `0.99`, `0.95` или `0.90`, а не точное `1.0`.

