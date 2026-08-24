# Testing and verification

Pick the cheapest check that can actually catch the mistake you might have made. The commands below
cover the usual scopes; they are a menu, not a requirement to run every suite.

## Common checks

```powershell
python -m pytest tests
python -m pytest tools\rhythm-lab\tests scripts\tests
npm --prefix .\frontend test
npm --prefix .\frontend run typecheck
npm --prefix .\frontend run build
npm --prefix .\docs\dj-track-similarity run check
git diff --check
```

The root Pytest configuration targets only `tests/`. Run helper-tool suites explicitly with
`python -m pytest tools/rhythm-lab/tests scripts/tests`.

Use the `ml`, `slow`, and `evaluation` markers only when the changed behavior
requires those optional dependencies or long-running paths.

`npm run check` runs strict Vale style checking for `README.md` plus the VitePress Markdown tree and
the site build. Run `npm run vale:sync` once after a fresh checkout or when `.vale.ini` packages
change. Use `npm run lint:style` when you want the same style report without failing the command.

## Focused examples

- Audio Doctor: `scripts\tests\test_repair_audio_metadata.py` and `tests\test_api_audio_doctor.py`.
- Audio Dedup: `scripts\tests\test_audio_dedup.py`.
- Rhythm Lab: `tools\rhythm-lab\tests\test_rhythm_lab.py`.
- SONARA runtime and storage: `tests\test_sonara_features.py`, `tests\test_sonara_native_batch.py`, and `tests\test_sonara_storage.py`.
- Tempo, Camelot, and transitions: `tests\test_tempo_resolution.py`, `tests\test_track_resolution.py`, and `tests\test_transition_diagnostics.py`.
- Classifier compatibility: `tests\test_classifier_productionization.py`, `tests\test_break_energy.py`, and `tools\rhythm-lab\tests\test_rhythm_lab.py`.

## Safety

Automated model, audio, and database tests use temporary SQLite and WAV fixtures
plus stubs. They must not use project databases, source music files, downloaded
model runs, or Audio Doctor and Audio Dedup apply modes.

## Manual behavior check

After a source behavior change, exercise the matching surface. Open UI work in a
browser and send a live HTTP request for API work. Invoke CLI commands directly,
or use a minimal import driver for library code. Cover one happy path and one
relevant failure path. Automated checks support this final exercise but do not
replace it.
