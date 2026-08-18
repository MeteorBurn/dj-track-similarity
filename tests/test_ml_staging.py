"""Tests for ML staging pipeline."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock

import numpy as np
import pytest
import torch

from dj_track_similarity.analysis_models import AnalysisCandidate, AnalysisTarget, AnalysisOutput
from dj_track_similarity.audio_loader import DecodedAudio
from dj_track_similarity.ml_staging import (
    MLStagingConfig,
    MLStagingSession,
    analyze_and_store_staged_ml,
)


def test_ml_staging_config_validation() -> None:
    """Test MLStagingConfig validates parameters correctly."""
    # Valid config
    config = MLStagingConfig(
        root=Path("/tmp/ml_staging"),
        copy_workers=2,
        decode_workers=2,
        stage_size=50,
        inference_batch_size=8,
        preflight_copy_enabled=True,
        preflight_copy_count=32,
    )
    assert config.copy_workers == 2
    assert config.decode_workers == 2
    assert config.stage_size == 50
    assert config.preflight_copy_count == 32

    # Zero workers should fail
    with pytest.raises(ValueError, match="copy_workers must be a positive integer"):
        MLStagingConfig(
            root=Path("/tmp/ml_staging"),
            copy_workers=0,
            decode_workers=2,
            stage_size=50,
            inference_batch_size=8,
        )

    with pytest.raises(ValueError, match="decode_workers must be a positive integer"):
        MLStagingConfig(
            root=Path("/tmp/ml_staging"),
            copy_workers=2,
            decode_workers=0,
            stage_size=50,
            inference_batch_size=8,
        )

    # Zero stage_size should fail
    with pytest.raises(ValueError, match="stage_size must be a positive integer"):
        MLStagingConfig(
            root=Path("/tmp/ml_staging"),
            copy_workers=2,
            decode_workers=2,
            stage_size=0,
            inference_batch_size=8,
        )

    # Zero inference_batch_size should fail
    with pytest.raises(ValueError, match="inference_batch_size must be a positive integer"):
        MLStagingConfig(
            root=Path("/tmp/ml_staging"),
            copy_workers=2,
            decode_workers=2,
            stage_size=50,
            inference_batch_size=0,
        )


def test_ml_staging_session_lifecycle(tmp_path: Path) -> None:
    """Test MLStagingSession cleanup lifecycle."""
    staging_root = tmp_path / "ml_staging"
    staging_root.mkdir()

    config = MLStagingConfig(
        root=staging_root,
        copy_workers=1,
        decode_workers=1,
        stage_size=10,
        inference_batch_size=4,
    )

    # Use context manager to trigger __enter__ which creates the path
    with MLStagingSession(config) as session:
        session_path = session.path

        # Session creates its own subdirectory under root
        assert session_path.exists()
        assert session_path.parent == staging_root
        assert session.config.root == staging_root

    # After context exit, cleanup removes the session subdirectory
    assert not session_path.exists()
    assert staging_root.exists()  # Root remains


@pytest.fixture
def mock_repository() -> MagicMock:
    """Create mock repository."""
    repo = MagicMock()
    return repo


@pytest.fixture
def mock_model_runner() -> MagicMock:
    """Create mock model runner."""
    runner = MagicMock()
    # Mock analyze_batch to return list of None (no errors)
    runner.analyze_batch = MagicMock(side_effect=lambda repo, items: [None] * len(items))
    return runner


@pytest.fixture
def mock_decode_fn(tmp_path: Path) -> Mock:
    """Create mock audio decode function."""
    def decode_audio(path: Path) -> DecodedAudio:
        # Return dummy DecodedAudio with correct structure
        return DecodedAudio(
            path=str(path),
            audio=torch.zeros((1, 44100), dtype=torch.float32),
            sample_rate=44100,
            detail="mock",
        )

    return Mock(side_effect=decode_audio)


def test_analyze_and_store_staged_ml_basic(
    tmp_path: Path,
    mock_repository: MagicMock,
    mock_model_runner: MagicMock,
    mock_decode_fn: Mock,
) -> None:
    """Test basic staged ML analysis flow."""
    staging_root = tmp_path / "ml_staging"
    staging_root.mkdir()

    # Create dummy source files
    source1 = tmp_path / "track1.mp3"
    source2 = tmp_path / "track2.mp3"
    source1.write_text("dummy audio 1")
    source2.write_text("dummy audio 2")

    config = MLStagingConfig(
        root=staging_root,
        copy_workers=1,
        decode_workers=1,
        stage_size=10,
        inference_batch_size=2,
    )

    target1 = AnalysisTarget(
        catalog_uuid="catalog-uuid",
        track_id=1,
        track_uuid="track-uuid-1",
    )
    target2 = AnalysisTarget(
        catalog_uuid="catalog-uuid",
        track_id=2,
        track_uuid="track-uuid-2",
    )

    candidates = [
        AnalysisCandidate(
            target=target1,
            file_path=str(source1),
            file_size_bytes=len("dummy audio 1"),
            file_modified_ns=0,
            missing_outputs=(AnalysisOutput(analysis_family="muq", output_kind="embedding"),),
        ),
        AnalysisCandidate(
            target=target2,
            file_path=str(source2),
            file_size_bytes=len("dummy audio 2"),
            file_modified_ns=0,
            missing_outputs=(AnalysisOutput(analysis_family="muq", output_kind="embedding"),),
        ),
    ]

    targets_by_track = {
        1: ("muq",),
        2: ("muq",),
    }

    model_runners = {"muq": mock_model_runner}

    # Run analysis
    analyze_and_store_staged_ml(
        repository=mock_repository,
        candidates=candidates,
        model_runners=model_runners,
        targets_by_track=targets_by_track,
        config=config,
        decode_audio=mock_decode_fn,
    )

    # Verify decode was called
    assert mock_decode_fn.call_count == 2

    # Verify model runner.analyze_batch was called
    assert mock_model_runner.analyze_batch.call_count >= 1


def test_analyze_and_store_staged_ml_refills_window_until_all_candidates_complete(
    tmp_path: Path,
    mock_repository: MagicMock,
    mock_model_runner: MagicMock,
    mock_decode_fn: Mock,
) -> None:
    """Staged analysis continues past one active staging window."""
    staging_root = tmp_path / "ml_staging"
    staging_root.mkdir()
    candidates = []
    targets_by_track = {}
    for track_id in range(1, 6):
        source = tmp_path / f"track{track_id}.mp3"
        source.write_text(f"dummy audio {track_id}")
        candidates.append(
            AnalysisCandidate(
                target=AnalysisTarget(
                    catalog_uuid="catalog-uuid",
                    track_id=track_id,
                    track_uuid=f"track-uuid-{track_id}",
                ),
                file_path=str(source),
                file_size_bytes=len(f"dummy audio {track_id}"),
                file_modified_ns=0,
                missing_outputs=(
                    AnalysisOutput(analysis_family="muq", output_kind="embedding"),
                ),
            )
        )
        targets_by_track[track_id] = ("muq",)

    completed_track_ids: list[int] = []
    results = analyze_and_store_staged_ml(
        repository=mock_repository,
        candidates=candidates,
        model_runners={"muq": mock_model_runner},
        targets_by_track=targets_by_track,
        config=MLStagingConfig(
            root=staging_root,
            copy_workers=1,
            decode_workers=1,
            stage_size=2,
            inference_batch_size=1,
        ),
        decode_audio=mock_decode_fn,
        track_result_callback=lambda result: completed_track_ids.append(
            result.candidate.target.track_id
        ),
    )

    assert [result.candidate.target.track_id for result in results] == [1, 2, 3, 4, 5]
    assert completed_track_ids == [1, 2, 3, 4, 5]
    assert mock_decode_fn.call_count == 5


def test_analyze_and_store_staged_ml_empty_queue(
    tmp_path: Path,
    mock_repository: MagicMock,
    mock_model_runner: MagicMock,
    mock_decode_fn: Mock,
) -> None:
    """Test staged ML analysis with no tracks to process."""
    staging_root = tmp_path / "ml_staging"
    staging_root.mkdir()

    config = MLStagingConfig(
        root=staging_root,
        copy_workers=1,
        decode_workers=1,
        stage_size=10,
        inference_batch_size=2,
    )

    # Empty queue
    candidates: list[AnalysisCandidate] = []
    targets_by_track: dict[int, tuple[str, ...]] = {}
    model_runners = {"muq": mock_model_runner}

    # Should complete without error
    analyze_and_store_staged_ml(
        repository=mock_repository,
        candidates=candidates,
        model_runners=model_runners,
        targets_by_track=targets_by_track,
        config=config,
        decode_audio=mock_decode_fn,
    )

    # No decode calls
    mock_decode_fn.assert_not_called()

    # No model calls
    mock_model_runner.assert_not_called()
