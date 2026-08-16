from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pytest

import dj_track_similarity.sonara_features as sonara_features_module
from dj_track_similarity.analysis_models import (
    AnalysisCandidate,
    AnalysisOutput,
    AnalysisTarget,
)
from dj_track_similarity.sonara_staging import (
    SonaraStagingConfig,
    SonaraStagingSession,
    StagedSonaraCandidate,
    StagedSonaraResult,
    analyze_and_store_staged_sonara,
    analyze_staged_sonara_group,
    cleanup_orphaned_sonara_staging,
)
from dj_track_similarity.sonara_runtime import SONARA_SAMPLE_RATE


def _candidate(track_id: int, source: Path) -> AnalysisCandidate:
    return AnalysisCandidate(
        target=AnalysisTarget(
            catalog_uuid="00000000-0000-0000-0000-000000000001",
            track_id=track_id,
            track_uuid=f"00000000-0000-0000-0000-{track_id:012d}",
        ),
        file_path=str(source),
        file_size_bytes=source.stat().st_size,
        file_modified_ns=source.stat().st_mtime_ns,
        missing_outputs=(
            AnalysisOutput("sonara", "core"),
            AnalysisOutput("sonara", "embedding"),
        ),
    )


def test_staging_session_preserves_source_identity_and_removes_copy(
    tmp_path: Path,
) -> None:
    source = tmp_path / "hdd" / "set" / "track.flac"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"original audio")
    candidate = _candidate(7, source)
    staging_root = tmp_path / "ssd"

    with SonaraStagingSession(SonaraStagingConfig(root=staging_root)) as session:
        staged = session.stage(candidate)

        assert staged.candidate is candidate
        assert staged.source_path == source
        assert staged.path != source
        assert staged.path.read_bytes() == b"original audio"
        assert source.read_bytes() == b"original audio"
        assert staged.path.is_relative_to(session.path)
        session.release(staged)
        assert not staged.path.exists()

    assert not any(staging_root.iterdir())


def test_staging_session_cleans_all_copies_when_copy_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "hdd" / "track.wav"
    source.parent.mkdir()
    source.write_bytes(b"original audio")
    candidate = _candidate(8, source)
    staging_root = tmp_path / "ssd"

    def _copy_then_fail(source_path: Path, destination: Path) -> None:
        destination.write_bytes(source_path.read_bytes())
        raise OSError("simulated SSD failure")

    with SonaraStagingSession(SonaraStagingConfig(root=staging_root)) as session:
        monkeypatch.setattr(session, "_copy", _copy_then_fail)
        with pytest.raises(OSError, match="simulated SSD failure"):
            session.stage(candidate)

    assert source.read_bytes() == b"original audio"
    assert not any(staging_root.iterdir())


def test_staged_ffmpeg_fallback_decodes_copy_but_logs_source_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = tmp_path / "hdd" / "track.flac"
    staged_path = tmp_path / "ssd" / "staged-track.flac"
    source.parent.mkdir()
    staged_path.parent.mkdir()
    source.write_bytes(b"source")
    staged_path.write_bytes(b"copy")
    candidate = _candidate(9, source)
    staged = StagedSonaraCandidate(
        candidate=candidate,
        source_path=source,
        path=staged_path,
    )
    native_paths: list[str] = []
    ffmpeg_paths: list[Path] = []

    class _FailedTrack(dict):
        @property
        def failed(self) -> bool:
            return True

    class _Sonara:
        @staticmethod
        def analyze_batch(paths, **_kwargs):
            native_paths.extend(paths)
            return [
                _FailedTrack(error_kind="decode", error="unsupported codec")
                for _path in paths
            ]

        @staticmethod
        def analyze_signal(_audio, **_kwargs):
            return {"energy": 0.5}

    monkeypatch.setattr(sonara_features_module, "_import_sonara", lambda: _Sonara)

    def decode_copy(path: str):
        ffmpeg_paths.append(Path(path))
        return np.asarray([0.1, -0.1], dtype=np.float32), SONARA_SAMPLE_RATE, "test"

    monkeypatch.setattr(
        sonara_features_module,
        "load_audio_mono_with_ffmpeg",
        decode_copy,
    )

    with caplog.at_level(logging.WARNING, logger="dj_track_similarity.sonara_features"):
        results = analyze_staged_sonara_group((staged,))

    assert native_paths == [str(staged_path)]
    assert ffmpeg_paths == [staged_path]
    assert results[0].candidate is candidate
    assert results[0].error is None
    assert results[0].used_ffmpeg_fallback
    assert f"path={source}" in caplog.text
    assert f"path={staged_path}" not in caplog.text


def test_staged_pipeline_stores_original_identity_and_isolates_failure(
    tmp_path: Path,
) -> None:
    source_one = tmp_path / "hdd" / "one.wav"
    source_two = tmp_path / "hdd" / "two.wav"
    source_one.parent.mkdir()
    source_one.write_bytes(b"one")
    source_two.write_bytes(b"two")
    candidates = (_candidate(1, source_one), _candidate(2, source_two))
    seen_paths: list[Path] = []
    saved_track_ids: list[int] = []
    stored_writes: list[int] = []
    completed_track_ids: list[int] = []

    class _Repository:
        def register_analysis_outputs(self, outputs):
            return tuple(f"{item.analysis_family}/{item.output_kind}" for item in outputs)

        def save_sonara_results(self, writes):
            saved_track_ids.extend(write.target.track_id for write in writes)
            from dj_track_similarity.analysis_models import AnalysisWriteResult

            return tuple(
                AnalysisWriteResult(target=write.target, written_outputs=write.outputs)
                for write in writes
            )

    def _analyze(staged):
        results = []
        for item in staged:
            seen_paths.append(item.path)
            if item.candidate.target.track_id == 2:
                results.append(StagedSonaraResult(item=item, error=RuntimeError("codec failed")))
            else:
                results.append(
                    StagedSonaraResult(
                        item=item,
                        analysis={"energy": 0.5},
                    )
                )
        return results

    outcomes = analyze_and_store_staged_sonara(
        _Repository(),
        candidates,
        config=SonaraStagingConfig(root=tmp_path / "ssd", stage_size=2),
        analyze_group=_analyze,
        prepare_write=lambda candidate, analysis: candidate.target.track_id,
        store_write=lambda repository, write: stored_writes.append(write),
        result_callback=lambda result: completed_track_ids.append(
            result.candidate.target.track_id
        ),
    )

    outcomes_by_track = {
        outcome.candidate.target.track_id: outcome for outcome in outcomes
    }
    assert set(outcomes_by_track) == {1, 2}
    assert outcomes_by_track[1].error is None
    assert "codec failed" in str(outcomes_by_track[2].error)
    assert seen_paths and all(path.parent.parent == tmp_path / "ssd" for path in seen_paths)
    assert all(path != source_one and path != source_two for path in seen_paths)
    assert saved_track_ids == []
    assert stored_writes == [1]
    assert completed_track_ids == [
        outcome.candidate.target.track_id for outcome in outcomes
    ]
    assert not any((tmp_path / "ssd").iterdir())


def test_staged_pipeline_never_exceeds_configured_resident_window(
    tmp_path: Path,
) -> None:
    sources = []
    for track_id in range(1, 5):
        source = tmp_path / "hdd" / f"{track_id}.wav"
        source.parent.mkdir(exist_ok=True)
        source.write_bytes(bytes([track_id]))
        sources.append(_candidate(track_id, source))
    observed_resident_counts: list[int] = []

    def _analyze(staged):
        observed_resident_counts.append(
            sum(path.name != ".owner" for path in staged[0].path.parent.iterdir())
        )
        return [
            StagedSonaraResult(item=item, analysis={"energy": 0.5})
            for item in staged
        ]

    analyze_and_store_staged_sonara(
        object(),
        sources,
        config=SonaraStagingConfig(
            root=tmp_path / "ssd",
            stage_size=2,
            copy_workers=1,
            processes=1,
            max_native_batch_size=1,
        ),
        analyze_group=_analyze,
        prepare_write=lambda candidate, analysis: candidate.target.track_id,
        store_write=lambda repository, write: None,
    )

    assert observed_resident_counts
    assert max(observed_resident_counts) <= 2


def test_staged_pipeline_cleans_copies_when_cancelled(tmp_path: Path) -> None:
    source = tmp_path / "hdd" / "cancel.wav"
    source.parent.mkdir()
    source.write_bytes(b"original audio")
    staging_root = tmp_path / "ssd"

    with pytest.raises(RuntimeError, match="staging cancelled"):
        analyze_and_store_staged_sonara(
            object(),
            (_candidate(1, source),),
            config=SonaraStagingConfig(root=staging_root),
            analyze_group=lambda staged: (),
            prepare_write=lambda candidate, analysis: None,
            store_write=lambda repository, write: None,
            cancelled=lambda: True,
        )

    assert source.read_bytes() == b"original audio"
    assert not any(staging_root.iterdir())


def test_orphan_cleanup_preserves_live_job_directories(tmp_path: Path) -> None:
    staging_root = tmp_path / "ssd"
    orphan = staging_root / "sonara-stage-orphan"
    live = staging_root / "sonara-stage-live"
    orphan.mkdir(parents=True)
    live.mkdir()
    (orphan / ".owner").write_text("99999999", encoding="ascii")
    (live / ".owner").write_text("4242", encoding="ascii")

    import dj_track_similarity.sonara_staging as staging_module

    original_exists = staging_module._process_exists
    staging_module._process_exists = lambda pid: pid == 4242
    try:
        cleanup_orphaned_sonara_staging(staging_root)
    finally:
        staging_module._process_exists = original_exists

    assert not orphan.exists()
    assert live.exists()


def test_orphan_cleanup_removes_empty_markerless_stage_directory(
    tmp_path: Path,
) -> None:
    staging_root = tmp_path / "ssd"
    empty_residue = staging_root / "sonara-stage-empty-residue"
    unowned_files = staging_root / "sonara-stage-unowned-files"
    empty_residue.mkdir(parents=True)
    unowned_files.mkdir()
    (unowned_files / "keep.wav").write_bytes(b"not owned by a staging session")

    cleanup_orphaned_sonara_staging(staging_root)

    assert not empty_residue.exists()
    assert unowned_files.exists()
