@echo off
cd /d "%~dp0.."
python -m uvicorn dj_track_similarity.api:create_app --factory --host 127.0.0.1 --port 8765
