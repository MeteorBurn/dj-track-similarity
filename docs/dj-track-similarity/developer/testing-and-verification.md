# Testing and verification

> Audience: Developers choosing checks after a change.
> Goal: Run focused verification that matches edit risk.
> Type: how-to

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

`npm run check` runs strict Vale style checking for `README.md` plus the VitePress Markdown tree and
the site build. Run `npm run vale:sync` once after a fresh checkout or when `.vale.ini` packages
change. Use `npm run lint:style` when you want the same style report without failing the command.

## Focused examples

- Audio Doctor: `scripts\tests\test_repair_audio_metadata.py` and `tests\test_api_audio_doctor.py`.
- Audio Dedup: `scripts\tests\test_audio_dedup.py`.
- Rhythm Lab: `tools\rhythm-lab\tests\test_rhythm_lab.py`.
- SONARA contract and storage: `tests\test_sonara_contract.py` and `tests\test_sonara_features.py`.
- Tempo, Camelot, SET, and transitions: `tests\test_tempo_resolution.py`, `tests\test_track_resolution.py`, `tests\test_set_builder.py`, and `tests\test_transition_diagnostics.py`.
- Classifier compatibility: `tests\test_classifier_productionization.py`, `tests\test_break_energy.py`, and `tools\rhythm-lab\tests\test_rhythm_lab.py`.

## Safety

Do not run destructive apply/delete modes as routine verification. Tests must use temporary databases.
