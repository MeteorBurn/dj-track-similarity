# CLAP audio-file experiment

`.djts/skills/text-music-search/scripts/score_prompt_bank.py` is a standalone **CLAP-only** experiment for
explicitly supplied audio files and a checkpoint. It is not the production
library search, a MuQ-MuLan audio runner, or an automatic model comparison tool.
It neither changes library rows nor writes tags to source audio.

## Inputs and environment

Use the existing root `.venv` and the dependency workflow in `AGENTS.md`. Check
the declared `uv` extras and local artifacts before any authorized environment
repair. Do not create a private environment or install packages through pip.

Use a reviewed CLAP bank in the [labels/prompts JSON format](prompt_banks.md#draft-json-and-validation).
Select an existing checkpoint consistent with the chosen architecture; consult
`src/dj_track_similarity/embedding/clap.py` for the application's current adapter
configuration rather than assuming a historical checkpoint is installed.

Before loading dependencies or model weights, the script validates the bank,
existing bank/checkpoint/audio files, and numeric arguments. Window and hop
durations must be finite and positive and produce at least one sample; alpha
must be finite and nonnegative. Output must differ from every input, including
paths that resolve through symbolic links or refer to the same hard-linked file.

The script temporarily forces `torch.load(..., weights_only=True)` while calling
the CLAP loader and restores the original function in `finally`. Unsupported
safe loading fails closed. Do not add an unsafe retry or weaken this guard to
make a checkpoint load.

## Invocation

Run from the repo root. In this example, `$clapDraftPath`, `$checkpointPath`, and
`$audioPaths` are user-authorized existing files verified with `Resolve-Path`;
`$scoreOutputPath` is a distinct new report path. Real audio/model execution is
performed only when the current task authorizes it.

```powershell
& .\.venv\Scripts\python.exe .djts/skills/text-music-search/scripts/score_prompt_bank.py `
  --prompt-bank $clapDraftPath --ckpt $checkpointPath --audio $audioPaths `
  --out $scoreOutputPath --amodel HTSAT-base --device cpu `
  --window-seconds 10 --hop-seconds 5 --alpha 0.35
```

The numeric values illustrate explicit experiment settings, not optimized
recommendations. Preserve the CLI arguments, checkpoint identity/hash, bank,
and audio identities alongside the output. `--help` is safe without loading
models. Use temporary audio and model stubs for automated verification.

## Algorithm and results

Read the script as the algorithm's source of truth. It decodes mono audio at
48 kHz, pads clips shorter than one window, and includes a final tail window
when the hop grid does not reach the end. It normalizes audio embeddings and
each positive text embedding, then normalizes their mean for each label.

For label `L` and window `w`:

```text
positive(w, L) = cosine(audio_window(w), normalized_mean(positive_prompts(L)))
negative(w, L) = max cosine(audio_window(w), each global or label hard negative)
final(w, L)    = positive(w, L) - alpha * negative(w, L)
```

No negative penalty is applied when a label has no negative bank or alpha is
zero. Production contrast retrieval instead pools the top two negative matches
and searches stored eligible vectors; the two paths are different experiments.

The JSON output retains `prompt_bank`, `checkpoint`, `amodel`, `enable_fusion`,
`alpha`, and `results`. Each audio result includes its window count/settings,
per-label positive/final distributions, optional negative distributions, and a
ranking. Distributions contain mean, median, top-20-percent mean, maximum, and
standard deviation. Ranking uses descending `final_top20_mean`; the top fraction
contains at least one window and rounds its count upward.

Window summaries describe this audio/checkpoint/bank configuration. They are
neither probabilities nor interchangeable with production search scores. Keep
this experiment's evidence separate when choosing a production text model.
