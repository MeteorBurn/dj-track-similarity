from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dj_track_similarity.ann_index import (
    clear_persistent_indexes,
    default_index_dir_for_repository,
)


def test_default_sidecar_path_and_clear_scope_are_safe(tmp_path: Path) -> None:
    repository = SimpleNamespace(path=tmp_path / "data" / "library.sqlite")
    index_dir = tmp_path / ".dj-track-similarity-indexes"
    index_dir.mkdir()
    kept_file = index_dir / "notes.txt"
    kept_subdir = index_dir / "nested"
    kept_file.write_text("keep\n", encoding="utf-8")
    kept_subdir.mkdir()
    mert_artifact = index_dir / "ann_mert_test.hnsw"
    mert_manifest = index_dir / "ann_mert_test.manifest.json"
    clap_artifact = index_dir / "ann_clap_test.hnsw"
    outside_file = tmp_path / "ann_mert_outside.hnsw"
    for path in (mert_artifact, mert_manifest, clap_artifact, outside_file):
        path.write_text("generated\n", encoding="utf-8")

    result = clear_persistent_indexes(index_dir, analysis_family="mert")

    assert default_index_dir_for_repository(repository) == (
        repository.path.parent / ".dj-track-similarity-indexes"
    )
    assert result.deleted_count == 2
    assert {path.name for path in result.deleted_files} == {
        mert_artifact.name,
        mert_manifest.name,
    }
    assert kept_file.exists()
    assert kept_subdir.exists()
    assert clap_artifact.exists()
    assert outside_file.exists()
