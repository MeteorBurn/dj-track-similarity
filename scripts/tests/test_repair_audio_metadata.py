from __future__ import annotations

import importlib.util
import time
import sys
from pathlib import Path


def _load_repair_module():
    path = Path(__file__).resolve().parents[1] / "repair_audio_metadata.py"
    spec = importlib.util.spec_from_file_location("repair_audio_metadata", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _aiff_chunk(chunk_id: bytes, payload: bytes) -> bytes:
    padding = b"\x00" if len(payload) % 2 else b""
    return chunk_id + len(payload).to_bytes(4, "big") + payload + padding


def _minimal_aiff_with_empty_id3_chunks() -> tuple[bytes, bytes]:
    ssnd_payload = b"\x00\x00\x00\x00\x00\x00\x00\x00" + b"\x01\x02\x03\x04"
    chunks = [
        _aiff_chunk(b"COMM", b"\x00\x02\x00\x00\x00\x01\x00\x10@\x0e\xacD\x00\x00\x00\x00\x00\x00"),
        _aiff_chunk(b"SSND", ssnd_payload),
        _aiff_chunk(b"ID3 ", b""),
        _aiff_chunk(b"ID3 ", b""),
        _aiff_chunk(b"ID3 ", b"ID3\x03\x00\x00\x00\x00\x00\x00"),
    ]
    body = b"AIFF" + b"".join(chunks)
    return b"FORM" + len(body).to_bytes(4, "big") + body, ssnd_payload


def test_log_collection_stays_limited_to_wav_post_save_readback(tmp_path: Path) -> None:
    repair = _load_repair_module()
    log_path = tmp_path / "app.log"
    wav_path = tmp_path / "bad.wav"
    aiff_path = tmp_path / "bad.aiff"
    flac_path = tmp_path / "bad.flac"
    log_path.write_text(
        "\n".join(
            [
                f"2026-05-24 02:09:50 ERROR dj_track_similarity.tags Genre tag apply failed track_id=1 path={wav_path} error=Genre tag was not readable after WAV save: {wav_path}",
                f"2026-05-24 02:10:00 ERROR dj_track_similarity.tags Genre tag apply failed track_id=2 path={aiff_path} error='{aiff_path}' ID3v2.32 not supported",
                f"2026-05-24 02:11:00 ERROR dj_track_similarity.tags Genre tag apply failed track_id=3 path={flac_path} error='{flac_path}' is not a valid FLAC file",
            ]
        ),
        encoding="utf-8",
    )

    assert repair.paths_from_log(log_path) == [wav_path]


def test_collect_paths_includes_audio_files_from_folder_recursively(tmp_path: Path) -> None:
    repair = _load_repair_module()
    root = tmp_path / "library"
    nested = root / "nested"
    nested.mkdir(parents=True)
    wav_path = root / "track.wav"
    aiff_path = nested / "track.aiff"
    ignored = nested / "notes.txt"
    wav_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    aiff_path.write_bytes(b"FORM\x00\x00\x00\x04AIFF")
    ignored.write_text("not audio", encoding="utf-8")

    paths = repair.collect_paths([], [], folders=[root], since=None, until=None)

    assert set(paths) == {wav_path, aiff_path}
    assert ignored not in paths


def test_mp3_content_with_flac_extension_is_reported_as_suspicious(tmp_path: Path) -> None:
    repair = _load_repair_module()
    audio_path = tmp_path / "wrong.flac"
    audio_path.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00")

    result = repair.inspect_file(audio_path)

    assert result.status == "suspicious"
    assert result.detected_format == "mp3"
    assert "extension=.flac" in result.message


def test_mp3_content_with_ogg_extension_is_reported_as_suspicious(tmp_path: Path) -> None:
    repair = _load_repair_module()
    audio_path = tmp_path / "wrong.ogg"
    audio_path.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x00")

    result = repair.inspect_file(audio_path)

    assert result.status == "suspicious"
    assert result.detected_format == "mp3"
    assert "extension=.ogg" in result.message


def test_ogg_container_with_opus_codec_is_allowed(monkeypatch, tmp_path: Path) -> None:
    repair = _load_repair_module()
    audio_path = tmp_path / "track.ogg"
    audio_path.write_bytes(b"OggS\x00\x02")
    monkeypatch.setattr(repair, "probe_file", lambda path: ("ogg", "opus"))
    monkeypatch.setattr(repair, "read_mutagen_tag_summary", lambda path: "mutagen ok tags=no")

    result = repair.inspect_file(audio_path)

    assert result.status == "ok"
    assert result.detected_format == "ogg"
    assert result.detected_codec == "opus"


def test_wav_container_with_flac_codec_is_reported_as_suspicious(monkeypatch, tmp_path: Path) -> None:
    repair = _load_repair_module()
    audio_path = tmp_path / "wrong.wav"
    audio_path.write_bytes(b"RIFF\x04\x00\x00\x00WAVE")
    monkeypatch.setattr(repair, "probe_file", lambda path: ("wav", "flac"))
    monkeypatch.setattr(repair, "read_mutagen_tag_summary", lambda path: "mutagen ok tags=no")

    result = repair.inspect_file(audio_path)

    assert result.status == "suspicious"
    assert result.detected_format == "wav"
    assert result.detected_codec == "flac"
    assert result.message == "extension=.wav detected_codec=flac"


def test_flac_container_with_vorbis_codec_is_reported_as_suspicious(monkeypatch, tmp_path: Path) -> None:
    repair = _load_repair_module()
    audio_path = tmp_path / "wrong.flac"
    audio_path.write_bytes(b"fLaC")
    monkeypatch.setattr(repair, "probe_file", lambda path: ("flac", "vorbis"))
    monkeypatch.setattr(repair, "read_mutagen_tag_summary", lambda path: "mutagen ok tags=no")

    result = repair.inspect_file(audio_path)

    assert result.status == "suspicious"
    assert result.detected_format == "flac"
    assert result.detected_codec == "vorbis"
    assert result.message == "extension=.flac detected_codec=vorbis"


def test_aiff_repair_removes_only_empty_id3_chunks_and_preserves_sound_payload() -> None:
    repair = _load_repair_module()
    data, ssnd_payload = _minimal_aiff_with_empty_id3_chunks()

    result = repair.repair_aiff_bytes(data)

    assert result.changed is True
    assert result.id3_seen == 3
    assert result.id3_removed == 2
    assert result.data.count(b"ID3 ") == 1
    assert ssnd_payload in result.data
    assert int.from_bytes(result.data[4:8], "big") == len(result.data) - 8


def test_wave_repair_reports_dropped_trailing_zero_padding() -> None:
    repair = _load_repair_module()
    data_payload = b"\x01\x02\x03\x04"
    body = b"WAVE" + b"data" + len(data_payload).to_bytes(4, "little") + data_payload + b"\x00"
    data = b"RIFF" + len(body).to_bytes(4, "little") + body

    result = repair.repair_wave_bytes(data)

    assert result.changed is True
    assert result.repaired_size == len(data) - 1
    assert "dropped trailing zero padding bytes at offset 24 size 1" in result.actions


def test_wave_file_with_only_trailing_zero_padding_is_notice(monkeypatch, tmp_path: Path) -> None:
    repair = _load_repair_module()
    audio_path = tmp_path / "track.wav"
    data_payload = b"\x01\x02\x03\x04"
    body = b"WAVE" + b"data" + len(data_payload).to_bytes(4, "little") + data_payload + b"\x00"
    audio_path.write_bytes(b"RIFF" + len(body).to_bytes(4, "little") + body)
    monkeypatch.setattr(repair, "mutagen_summary", lambda data: "mutagen ok tags=no")

    result = repair.repair_file(
        audio_path,
        apply_changes=False,
        backup_dir=None,
        no_backup=False,
        keep_id3="first",
    )

    assert result.status == "notice"
    assert result.message == "cosmetic trailing zero padding"
    assert result.original_size == len(audio_path.read_bytes())
    assert result.repaired_size == len(audio_path.read_bytes())
    assert result.actions == ["dropped trailing zero padding bytes"]


def test_main_output_includes_total_and_track_number(monkeypatch, tmp_path: Path, capsys) -> None:
    repair = _load_repair_module()
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"

    def fake_repair_file(path: Path, **_kwargs):
        return repair.FileRepairResult(
            path=path,
            status="ok",
            message="ok",
            original_size=10,
            repaired_size=10,
            mutagen_summary="mutagen ok tags=yes",
        )

    monkeypatch.setattr(repair, "repair_file", fake_repair_file)

    exit_code = repair.main([str(first), str(second), "--no-file-log"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Total tracks: 2" in output
    assert "[1/2] OK" in output
    assert "[2/2] OK" in output


def test_main_output_groups_problem_summary(monkeypatch, tmp_path: Path, capsys) -> None:
    repair = _load_repair_module()
    wav_path = tmp_path / "repair.wav"
    flac_path = tmp_path / "wrong.flac"
    tag_path = tmp_path / "tags.aiff"
    results = {
        wav_path: repair.FileRepairResult(
            path=wav_path,
            status="repairable",
            message="ok",
            original_size=20,
            repaired_size=18,
            actions=["shrunk oversized data chunk at offset 36 from declared size 100 to 80"],
        ),
        flac_path: repair.FileRepairResult(
            path=flac_path,
            status="suspicious",
            message="extension=.flac detected=mp3",
        ),
        tag_path: repair.FileRepairResult(
            path=tag_path,
            status="tag-error",
            message="mutagen error: ID3v2.32 not supported",
        ),
    }

    def fake_repair_file(path: Path, **_kwargs):
        return results[path]

    monkeypatch.setattr(repair, "repair_file", fake_repair_file)

    exit_code = repair.main([str(wav_path), str(flac_path), str(tag_path), "--no-file-log"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Problem summary:" in output
    assert "repairable: WAV oversized data chunk before ID3 chunk: 1" in output
    assert "suspicious: extension mismatch: .flac detected as mp3: 1" in output
    assert "tag-error: mutagen error: ID3v2.32 not supported: 1" in output


def test_format_result_uses_compact_one_line_layout(tmp_path: Path) -> None:
    repair = _load_repair_module()
    result = repair.FileRepairResult(
        path=tmp_path / "track.wav",
        status="repairable",
        message="ok",
        original_size=20,
        repaired_size=18,
        id3_seen=2,
        id3_removed=1,
        mutagen_summary="mutagen ok tags=yes keys=TCON",
        actions=["shrunk oversized data chunk", "normalized RIFF root size"],
    )

    output = repair.format_result(result, dry_run=True, index=1, total=10, color=False)

    assert "\n" not in output
    assert output.startswith("[1/10] REPAIRABLE")
    assert "mode=dry-run" in output
    assert "file=" in output
    assert "size=20->18" in output
    assert "id3=2/1" in output
    assert "action=shrunk oversized data chunk" in output
    assert "normalized RIFF root size" not in output


def test_format_result_can_color_status(tmp_path: Path) -> None:
    repair = _load_repair_module()
    result = repair.FileRepairResult(path=tmp_path / "track.flac", status="suspicious", message="extension mismatch")

    output = repair.format_result(result, dry_run=True, index=1, total=1, color=True)

    assert "\x1b[" in output
    assert "SUSPICIOUS" in output


def test_main_writes_file_log_for_each_processed_track(monkeypatch, tmp_path: Path, capsys) -> None:
    repair = _load_repair_module()
    first = tmp_path / "first.wav"
    second = tmp_path / "second.wav"
    file_log = tmp_path / "repair.log"
    file_log.write_text("old log content\n", encoding="utf-8")

    def fake_repair_file(path: Path, **_kwargs):
        return repair.FileRepairResult(path=path, status="ok", message="ok")

    monkeypatch.setattr(repair, "repair_file", fake_repair_file)

    exit_code = repair.main([str(first), str(second), "--file-log", str(file_log), "--color", "always"])

    assert exit_code == 0
    stdout = capsys.readouterr().out
    log_text = file_log.read_text(encoding="utf-8")
    assert "old log content" not in log_text
    assert "[1/2] OK" in log_text
    assert "[2/2] OK" in log_text
    assert "\x1b[" not in log_text
    assert "[1/2]" in stdout


def test_folder_state_skips_checked_files_and_processes_new_files(monkeypatch, tmp_path: Path, capsys) -> None:
    repair = _load_repair_module()
    folder = tmp_path / "library"
    folder.mkdir()
    first = folder / "first.wav"
    second = folder / "second.wav"
    first.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    state_path = tmp_path / "state.json"
    processed: list[Path] = []

    def fake_repair_file(path: Path, **_kwargs):
        processed.append(path)
        return repair.FileRepairResult(path=path, status="ok", message="ok")

    monkeypatch.setattr(repair, "repair_file", fake_repair_file)

    first_exit = repair.main(["--folder", str(folder), "--state", str(state_path), "--no-file-log"])
    second.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    second_exit = repair.main(["--folder", str(folder), "--state", str(state_path), "--no-file-log"])

    output = capsys.readouterr().out
    assert first_exit == 0
    assert second_exit == 0
    assert processed == [first, second]
    assert state_path.exists()
    assert "Already checked from state: 1" in output
    assert "Pending tracks: 1" in output


def test_default_folder_state_path_is_folder_dependent_and_reused(monkeypatch, tmp_path: Path, capsys) -> None:
    repair = _load_repair_module()
    run_dir = tmp_path / "audio_repair"
    monkeypatch.setattr(repair, "DEFAULT_RUN_DIR", run_dir)
    first_folder = tmp_path / "library-a"
    second_folder = tmp_path / "library-b"
    first_folder.mkdir()
    second_folder.mkdir()
    first_track = first_folder / "first.wav"
    second_track = second_folder / "second.wav"
    first_track.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    second_track.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    first_state = repair.resolve_state_path(None, [first_folder])
    second_state = repair.resolve_state_path(None, [second_folder])
    processed: list[Path] = []

    def fake_repair_file(path: Path, **_kwargs):
        processed.append(path)
        return repair.FileRepairResult(path=path, status="ok", message="ok")

    monkeypatch.setattr(repair, "repair_file", fake_repair_file)

    first_exit = repair.main(["--folder", str(first_folder), "--no-file-log"])
    repeat_exit = repair.main(["--folder", str(first_folder), "--no-file-log"])
    second_exit = repair.main(["--folder", str(second_folder), "--no-file-log"])

    output = capsys.readouterr().out
    assert first_exit == 0
    assert repeat_exit == 0
    assert second_exit == 0
    assert first_state == repair.resolve_state_path(None, [first_folder])
    assert second_state == repair.resolve_state_path(None, [second_folder])
    assert first_state != second_state
    assert first_state.exists()
    assert second_state.exists()
    assert processed == [first_track, second_track]
    assert f"State file: {first_state}" in output
    assert "Already checked from state: 1" in output


def test_default_backup_dir_is_under_script_work_dir(monkeypatch, tmp_path: Path) -> None:
    repair = _load_repair_module()
    backup_dir = tmp_path / "audio_repair" / "backups"
    audio_path = tmp_path / "track.wav"
    audio_bytes = b"RIFF\x00\x00\x00\x00WAVE"
    audio_path.write_bytes(audio_bytes)
    monkeypatch.setattr(repair, "DEFAULT_BACKUP_DIR", backup_dir)

    backup_path = repair.create_backup(audio_path, backup_dir=None, no_backup=False)

    assert backup_path is not None
    assert backup_path.parent == backup_dir
    assert backup_path.name.startswith("track.")
    assert backup_path.name.endswith(".wav.bak")
    assert backup_path.read_bytes() == audio_bytes


def test_folder_state_dry_run_does_not_skip_later_apply(monkeypatch, tmp_path: Path) -> None:
    repair = _load_repair_module()
    folder = tmp_path / "library"
    folder.mkdir()
    audio_path = folder / "track.wav"
    audio_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    state_path = tmp_path / "state.json"
    calls: list[bool] = []

    def fake_repair_file(path: Path, *, apply_changes: bool, **_kwargs):
        calls.append(apply_changes)
        return repair.FileRepairResult(
            path=path,
            status="repairable" if not apply_changes else "repaired",
            message="ok",
        )

    monkeypatch.setattr(repair, "repair_file", fake_repair_file)

    dry_run_exit = repair.main(["--folder", str(folder), "--state", str(state_path), "--no-file-log"])
    apply_exit = repair.main(["--folder", str(folder), "--state", str(state_path), "--no-file-log", "--apply"])
    second_apply_exit = repair.main(["--folder", str(folder), "--state", str(state_path), "--no-file-log", "--apply"])

    assert dry_run_exit == 0
    assert apply_exit == 0
    assert second_apply_exit == 0
    assert calls == [False, True]


def test_folder_dry_run_workers_process_multiple_files(monkeypatch, tmp_path: Path) -> None:
    repair = _load_repair_module()
    folder = tmp_path / "library"
    folder.mkdir()
    paths = [folder / f"track-{index}.wav" for index in range(4)]
    for path in paths:
        path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    calls: list[Path] = []

    def fake_repair_file(path: Path, **_kwargs):
        time.sleep(0.01)
        calls.append(path)
        return repair.FileRepairResult(path=path, status="ok", message="ok")

    monkeypatch.setattr(repair, "repair_file", fake_repair_file)

    exit_code = repair.main(
        ["--folder", str(folder), "--workers", "2", "--state", str(tmp_path / "state.json"), "--no-file-log"]
    )

    assert exit_code == 0
    assert sorted(calls) == paths


def test_apply_forces_single_worker(monkeypatch, tmp_path: Path) -> None:
    repair = _load_repair_module()
    folder = tmp_path / "library"
    folder.mkdir()
    paths = [folder / f"track-{index}.wav" for index in range(2)]
    for path in paths:
        path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    calls: list[Path] = []

    def fake_repair_file(path: Path, **_kwargs):
        calls.append(path)
        return repair.FileRepairResult(path=path, status="repaired", message="ok")

    monkeypatch.setattr(repair, "repair_file", fake_repair_file)

    exit_code = repair.main(
        ["--folder", str(folder), "--workers", "4", "--apply", "--state", str(tmp_path / "state.json"), "--no-file-log"]
    )

    assert exit_code == 0
    assert calls == paths
