# Testing and verification

> Audience: Developers choosing checks after a change.
> Goal: Run focused verification that matches edit risk.
> Type: how-to

## Common checks

```powershell
.\.venv\Scripts\python.exe -m pytest
cd frontend
npm run build
cd ..\docs\dj-track-similarity
npm run build
```

## Focused examples

- Audio Doctor: `scripts\tests\test_repair_audio_metadata.py` and `tests\test_api_audio_doctor.py`.
- Audio Dedup: `scripts\tests\test_audio_dedup.py`.
- Rhythm Lab: `tools\rhythm-lab\tests\test_rhythm_lab.py`.

## Safety

Do not run destructive apply/delete modes as routine verification. Tests must use temporary databases.
