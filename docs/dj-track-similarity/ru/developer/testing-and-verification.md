# Testing and verification

Аудитория: contributors and AI agents  
Цель: выбрать smallest verification proving the change  
Тип: how-to/reference

Use risk-based verification. Do not run largest suite by default when focused
check proves touched behavior.

## Backend changes

Run focused pytest for touched module or endpoint. Use full suite for broad
schema, database, concurrency or shared infrastructure changes.

## Frontend changes

Run:

```powershell
cd frontend
npm run build
```

For visual or interaction changes, also smoke test relevant UI in browser
against safe database.

## Docs changes

Run:

```powershell
cd docs\dj-track-similarity
npm run build
```

Use markdown/link/spell checks when configured and useful for changed pages.

## Helper scripts

Repair-script focused test:

```powershell
python -m pytest scripts\tests\test_repair_audio_metadata.py --override-ini addopts=
```

Audio dedup focused test:

```powershell
python -m pytest scripts\tests\test_audio_dedup.py --override-ini addopts=
```

Rhythm Lab focused test:

```powershell
python -m pytest tools\rhythm-lab\tests\test_rhythm_lab.py --override-ini addopts=
```

## Real user data

Do not use real library databases for automated tests. Use temporary databases,
copies or explicit user-provided paths for manual checks.
