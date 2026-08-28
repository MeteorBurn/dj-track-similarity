# Testing and verification

The commands below cover the usual scopes. They are a menu rather than a requirement to run every
suite.

## Common checks

```powershell
python -m pytest tests
python -m pytest tools\rhythm-lab\tests tools\audio-dedup\tests tools\audio-online\tests scripts\tests
npm --prefix .\frontend test
npm --prefix .\frontend run typecheck
npm --prefix .\frontend run build
npm --prefix .\docs\dj-track-similarity run check
git diff --check
```

The root Pytest configuration targets only `tests/`. Four other suites need naming on the command
line:

| Suite | Files | Covers |
| --- | ---: | --- |
| `tools/rhythm-lab/tests` | 3 | labelling, training, promotion, label transfer, Lab consumers |
| `tools/audio-dedup/tests` | 4 | CLI output, fingerprint candidates, the fingerprint benchmark, the spectral check |
| `tools/audio-online/tests` | 11 | config, auth, CLI, inputs, matching, sources, report, workbook format, HTTP |
| `scripts/tests` | 7 | Audio Doctor repair, database optimization, database QA, the LAN launcher, dedup, the CLAP checkpoint embedder, the search benchmark |

Frontend tests run with `node --test tests/*.test.mjs` from `frontend/`. One of them,
`frontend/tests/testsExecuteCode.test.mjs`, is a meta-guard rather than a feature test: it fails when
a test asserts on the text of a source file instead of driving the module. Read it before adding a
frontend test.

Use the `ml`, `slow`, and `evaluation` markers only when the changed behavior
requires those optional dependencies or long-running paths.

`npm run check` runs strict Vale style checking for `README.md` plus the VitePress Markdown tree and
the site build. Run `npm run vale:sync` once after a fresh checkout or when `.vale.ini` packages
change. Use `npm run lint:style` when you want the same style report without failing the command.

## Focused examples

- Audio Doctor: `scripts\tests\test_repair_audio_metadata.py`. Audio Doctor has no API route and no
  API test.
- Audio Dedup: `scripts\tests\test_audio_dedup.py`, `tools\audio-dedup\tests`, and
  `tests\test_api_audio_dedup.py`.
- Analysis staging: `tests\test_sonara_staging.py` and `tests\test_ml_staging.py`.
- Text search: `tests\test_api_text_search.py`, which also pins the warmup and feedback routes.
- Database validation: `tests\test_api_database_validation.py` and
  `tests\test_database_validation_jobs.py`.
- Supported formats: `tests\test_supported_audio_formats.py`, which pins all 14 extensions.
- Rhythm Lab: `tools\rhythm-lab\tests\test_rhythm_lab.py`.
- SONARA runtime and storage: `tests\test_sonara_features.py`, `tests\test_sonara_native_batch.py`, and `tests\test_sonara_storage.py`.
- Tempo, Camelot, and transitions: `tests\test_tempo_resolution.py`, `tests\test_track_resolution.py`, and `tests\test_transition_diagnostics.py`.
- Classifier compatibility: `tests\test_classifier_productionization.py`, `tests\test_break_energy.py`, and `tools\rhythm-lab\tests\test_rhythm_lab.py`.

## Safety

Automated model, audio, and database tests use temporary SQLite and WAV fixtures
plus stubs. They must not use project databases, source music files, downloaded
model runs, or Audio Doctor and Audio Dedup apply modes.

## Clean-machine backstop

`.github/workflows/ci.yml` runs the same suites on empty Windows runners. It is manual only, started
from the Actions tab, and its scope is the base install plus `dev` and `rhythm-lab`. The `ml` extra
stays out, so torch, CUDA wheels, and model checkpoints are absent and the tests that need torch skip
themselves. Use it before a release, or when something works locally and you suspect the local
environment is why.

## Manual behavior check

After a source behavior change, exercise the matching surface. Open UI work in a
browser and send a live HTTP request for API work. Invoke CLI commands directly,
or use a minimal import driver for library code. Cover one happy path and one
relevant failure path. Automated checks support this final exercise but do not
replace it.
