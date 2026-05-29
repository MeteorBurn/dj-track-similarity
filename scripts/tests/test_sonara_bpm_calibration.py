from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np


def test_harmonic_candidates_and_best_by_tag() -> None:
    module = _load_script()

    candidates = module.harmonic_candidates(258.398, min_bpm=60.0, max_bpm=190.0)
    values = {round(candidate.value, 3) for candidate in candidates}

    assert 129.199 in values
    assert 86.133 in values
    assert module.best_candidate_by_tag(candidates, 126.0).value == 129.199


def test_tagless_prior_prefers_library_typical_candidate() -> None:
    module = _load_script()
    candidates = module.harmonic_candidates(258.398, min_bpm=60.0, max_bpm=190.0)

    selected = module.select_tagless_candidate(candidates, library_median_bpm=128.0)

    assert round(selected.value, 3) == 129.199


def test_target_sample_rate_uses_half_native_for_standard_rates() -> None:
    module = _load_script()

    assert module.target_sample_rate_for_native(44100) == 22050
    assert module.target_sample_rate_for_native(48000) == 24000
    assert module.target_sample_rate_for_native(96000) == 48000
    assert module.target_sample_rate_for_native(49000) == 24000
    assert module.target_sample_rate_for_native(43000) == 22050


def test_run_calibration_writes_reports(tmp_path: Path) -> None:
    module = _load_script()
    db_path = tmp_path / "library.sqlite"
    audio_one = tmp_path / "one.wav"
    audio_two = tmp_path / "two.wav"
    audio_one.write_bytes(b"fake")
    audio_two.write_bytes(b"fake")
    _create_db(
        db_path,
        [
            (1, str(audio_one), {"bpm": "126", "sonara_features": {"bpm": {"value": 258.398}}}),
            (2, str(audio_two), {"bpm": "91", "sonara_features": {"bpm": {"value": 184.57}}}),
        ],
    )
    reports_dir = tmp_path / "reports"

    result = module.run_calibration(
        db_path=db_path,
        reports_dir=reports_dir,
        limit=2,
        sample_mode="all",
        seed=7,
        sonara_module=FakeSonara(),
    )

    assert result.summary["tracks_evaluated"] == 2
    assert result.summary["native_sample_rates"] == {"48000": 1, "44100": 1}
    assert result.json_path.exists()
    assert result.csv_path.exists()
    assert result.md_path.exists()
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["summary"]["target_sample_rate_policy"] == "nearest_standard_half_sample_rate"
    assert payload["tracks"][0]["native_sample_rate"] in {44100, 48000}
    assert {track["normalized_sample_rate"] for track in payload["tracks"]} == {44100, 48000}
    assert {track["target_sample_rate"] for track in payload["tracks"]} == {22050, 24000}
    assert "tagless_prior" in payload["tracks"][0]["strategies"]
    assert "mean_abs_error" in result.md_path.read_text(encoding="utf-8")


class FakeSonara:
    def load(self, path: str, *, sr: int = 22050, mono: bool = True):
        native = 48000 if path.endswith("one.wav") else 44100
        length = 2048 if path.endswith("one.wav") else 1024
        samples = np.zeros(length, dtype=np.float32)
        return samples, native

    def resample(self, y, *, orig_sr: int, target_sr: int):
        return np.zeros(target_sr // 10, dtype=np.float32)

    def analyze_signal(self, y, *, sr: int = 22050, mode: str = "compact"):
        return {"bpm": 258.398 if sr == 24000 else 184.57, "n_beats": 16}

    def beat_track(self, *, y=None, onset_envelope=None, sr=22050, hop_length=512, start_bpm=120.0, tightness=100.0, trim=True):
        return start_bpm, [0, 10, 20]


def _create_db(db_path: Path, rows: list[tuple[int, str, dict[str, object]]]) -> None:
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE tracks (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime REAL NOT NULL,
                artist TEXT,
                title TEXT,
                album TEXT,
                bpm REAL,
                musical_key TEXT,
                energy REAL,
                duration REAL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        for track_id, path, metadata in rows:
            connection.execute(
                """
                INSERT INTO tracks (id, path, size, mtime, artist, title, bpm, metadata_json)
                VALUES (?, ?, 1, 1.0, ?, ?, NULL, ?)
                """,
                (track_id, path, f"Artist {track_id}", f"Title {track_id}", json.dumps(metadata)),
            )


def _load_script():
    path = Path(__file__).resolve().parents[1] / "sonara_bpm_calibration.py"
    spec = importlib.util.spec_from_file_location("sonara_bpm_calibration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
