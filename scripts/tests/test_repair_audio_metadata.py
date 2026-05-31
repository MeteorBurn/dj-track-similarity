from __future__ import annotations

import importlib.util
import json
import sqlite3
import sys
import time
from pathlib import Path
import zipfile


def _load_repair_module():
    path = Path(__file__).resolve().parents[1] / "audio_repair" / "repair_audio_metadata.py"
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

    exit_code = repair.main([str(first), str(second), "--no-file-log", "--no-report"])

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

    exit_code = repair.main([str(wav_path), str(flac_path), str(tag_path), "--no-file-log", "--no-report"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Problem summary:" in output
    assert "repairable[OVERSIZED_DATA]: WAV oversized data chunk before ID3 chunk: 1" in output
    assert "suspicious[EXTENSION_MISMATCH]: extension mismatch: .flac detected as mp3: 1" in output
    assert "tag-error[TAG_ERROR]: mutagen error: ID3v2.32 not supported: 1" in output


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

    exit_code = repair.main([str(first), str(second), "--file-log", str(file_log), "--color", "always", "--no-report"])

    assert exit_code == 0
    stdout = capsys.readouterr().out
    log_text = file_log.read_text(encoding="utf-8")
    assert "old log content" not in log_text
    assert "[1/2] OK" in log_text
    assert "[2/2] OK" in log_text
    assert "\x1b[" not in log_text
    assert "[1/2]" in stdout


def test_main_writes_audio_repair_report_bundle(monkeypatch, tmp_path: Path, capsys) -> None:
    repair = _load_repair_module()
    out_dir = tmp_path / "reports"
    wav_path = tmp_path / "repair.wav"
    flac_path = tmp_path / "wrong.flac"

    def fake_repair_file(path: Path, **_kwargs):
        if path == wav_path:
            return repair.FileRepairResult(
                path=path,
                status="repairable",
                message="ok",
                original_size=20,
                repaired_size=18,
                id3_seen=2,
                id3_removed=1,
                mutagen_summary="mutagen ok tags=yes keys=TCON",
                actions=["shrunk oversized data chunk at offset 36 from declared size 100 to 80"],
            )
        return repair.FileRepairResult(
            path=path,
            status="suspicious",
            message="extension=.flac detected=mp3",
        )

    monkeypatch.setattr(repair, "repair_file", fake_repair_file)

    exit_code = repair.main([str(wav_path), str(flac_path), "--out-dir", str(out_dir), "--no-file-log"])

    assert exit_code == 0
    stdout = capsys.readouterr().out
    report_paths = sorted(out_dir.glob("audio_repair_report_*.json"))
    assert len(report_paths) == 1
    json_path = report_paths[0]
    xlsx_path = json_path.with_suffix(".xlsx")
    log_path = json_path.with_suffix(".log")
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "dry-run"
    assert payload["result_count"] == 2
    assert payload["status_counts"] == {"repairable": 1, "suspicious": 1}
    assert payload["reason_counts"] == {"EXTENSION_MISMATCH": 1, "OVERSIZED_DATA": 1}
    assert payload["results"][0]["path"] == str(wav_path)
    assert payload["results"][0]["reason"] == "OVERSIZED_DATA"
    assert payload["results"][0]["action"] == "REPAIR AVAILABLE"
    assert payload["results"][1]["action"] == "REVIEW MANUALLY"
    assert "groups" not in payload
    assert "rhythm_lab" not in payload
    assert xlsx_path.exists()
    assert log_path.exists()
    with zipfile.ZipFile(xlsx_path) as archive:
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        summary_xml = archive.read("xl/worksheets/sheet1.xml").decode("utf-8")
        results_xml = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
    assert "Summary" in workbook_xml
    assert "Results" in workbook_xml
    assert "Problems" in workbook_xml
    assert "Audio repair summary" in summary_xml
    assert "Duplicate audio summary" not in summary_xml
    assert "REPAIR AVAILABLE" in results_xml
    assert "OVERSIZED_DATA" in results_xml
    log_text = log_path.read_text(encoding="utf-8")
    assert "audio_repair dry-run run" in log_text
    assert "status_count_repairable=1" in log_text
    assert "reason_count_OVERSIZED_DATA=1" in log_text
    assert f"json={json_path}" in stdout
    assert f"xlsx={xlsx_path}" in stdout
    assert f"log={log_path}" in stdout


def test_report_includes_current_state_entries_for_skipped_files(monkeypatch, tmp_path: Path) -> None:
    repair = _load_repair_module()
    folder = tmp_path / "library"
    folder.mkdir()
    ok_path = folder / "checked.wav"
    repair_path = folder / "repair.wav"
    ok_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    repair_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    state_path = tmp_path / "state.json"
    out_dir = tmp_path / "reports"

    def fake_repair_file(path: Path, **_kwargs):
        if path == repair_path:
            return repair.FileRepairResult(
                path=path,
                status="repairable",
                message="ok",
                original_size=20,
                repaired_size=18,
                actions=["shrunk oversized data chunk at offset 36 from declared size 100 to 80"],
            )
        return repair.FileRepairResult(path=path, status="ok", message="ok", original_size=20, repaired_size=20)

    monkeypatch.setattr(repair, "repair_file", fake_repair_file)

    first_exit = repair.main(["--folder", str(folder), "--state", str(state_path), "--no-file-log", "--no-report"])
    second_exit = repair.main(
        ["--folder", str(folder), "--state", str(state_path), "--out-dir", str(out_dir), "--no-file-log"]
    )

    report_paths = sorted(out_dir.glob("audio_repair_report_*.json"))
    payload = json.loads(report_paths[0].read_text(encoding="utf-8"))
    results = {Path(result["path"]): result for result in payload["results"]}
    assert first_exit == 0
    assert second_exit == 0
    assert payload["processed_count"] == 0
    assert payload["result_count"] == 2
    assert payload["state"]["skipped_from_state"] == 2
    assert payload["state"]["included_in_report"] == 2
    assert payload["status_counts"] == {"ok": 1, "repairable": 1}
    assert payload["reason_counts"] == {"OVERSIZED_DATA": 1}
    assert results[ok_path]["source"] == "state"
    assert results[ok_path]["action"] == "OK"
    assert results[ok_path]["mode"] == "dry-run"
    assert results[repair_path]["source"] == "state"
    assert results[repair_path]["action"] == "REPAIR AVAILABLE"
    assert results[repair_path]["reason"] == "OVERSIZED_DATA"


def test_apply_skips_nonrepairable_dry_run_state_and_reports_repaired_state(
    monkeypatch, tmp_path: Path
) -> None:
    repair = _load_repair_module()
    folder = tmp_path / "library"
    folder.mkdir()
    ok_path = folder / "checked.wav"
    repair_path = folder / "repair.wav"
    ok_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    repair_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    state_path = tmp_path / "state.json"
    out_dir = tmp_path / "reports"
    repeat_out_dir = tmp_path / "repeat-reports"
    calls: list[tuple[Path, bool]] = []

    def fake_repair_file(path: Path, *, apply_changes: bool, **_kwargs):
        calls.append((path, apply_changes))
        if path == repair_path:
            if apply_changes:
                path.write_bytes(b"RIFF\x06\x00\x00\x00WAVEfx")
                return repair.FileRepairResult(
                    path=path,
                    status="repaired",
                    message="ok",
                    original_size=20,
                    repaired_size=18,
                    actions=["shrunk oversized data chunk at offset 36 from declared size 100 to 80"],
                )
            return repair.FileRepairResult(
                path=path,
                status="repairable",
                message="ok",
                original_size=20,
                repaired_size=18,
                actions=["shrunk oversized data chunk at offset 36 from declared size 100 to 80"],
            )
        return repair.FileRepairResult(path=path, status="ok", message="ok", original_size=20, repaired_size=20)

    monkeypatch.setattr(repair, "repair_file", fake_repair_file)

    dry_run_exit = repair.main(["--folder", str(folder), "--state", str(state_path), "--no-file-log", "--no-report"])
    apply_exit = repair.main(
        [
            "--folder",
            str(folder),
            "--state",
            str(state_path),
            "--apply",
            "--out-dir",
            str(out_dir),
            "--no-file-log",
        ]
    )
    repeat_apply_exit = repair.main(
        [
            "--folder",
            str(folder),
            "--state",
            str(state_path),
            "--apply",
            "--out-dir",
            str(repeat_out_dir),
            "--no-file-log",
        ]
    )

    payload = json.loads(sorted(out_dir.glob("audio_repair_report_*.json"))[0].read_text(encoding="utf-8"))
    repeat_payload = json.loads(
        sorted(repeat_out_dir.glob("audio_repair_report_*.json"))[0].read_text(encoding="utf-8")
    )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    entries = {entry["title"]: entry for entry in state["files"].values()}
    repeat_results = {Path(result["path"]): result for result in repeat_payload["results"]}
    assert dry_run_exit == 0
    assert apply_exit == 0
    assert repeat_apply_exit == 0
    assert calls == [(ok_path, False), (repair_path, False), (repair_path, True)]
    assert payload["processed_count"] == 1
    assert payload["result_count"] == 2
    assert payload["status_counts"] == {"ok": 1, "repaired": 1}
    assert entries["repair.wav"]["mode"] == "apply"
    assert entries["repair.wav"]["status"] == "REPAIRED"
    assert entries["repair.wav"]["message"] == "repair_applied"
    assert repeat_payload["processed_count"] == 0
    assert repeat_payload["result_count"] == 2
    assert repeat_payload["status_counts"] == {"ok": 1, "repaired": 1}
    assert repeat_results[repair_path]["source"] == "state"
    assert repeat_results[repair_path]["action"] == "ALREADY REPAIRED"
    assert repeat_results[repair_path]["mode"] == "apply"


def test_xlsx_report_escapes_xml_invalid_control_characters(tmp_path: Path) -> None:
    repair = _load_repair_module()
    xlsx_path = tmp_path / "report.xlsx"
    payload = {
        "mode": "dry-run",
        "generated_at": "2026-05-29T12:00:00",
        "source_counts": {"paths": 1, "folders": 0, "databases": 0, "logs": 0},
        "options": {"keep_id3": "first", "workers": 1, "backup_dir": "", "no_backup": False},
        "state": {"enabled": False, "path": None, "skipped_from_state": 0, "skipped_by_reason": 0},
        "total_collected": 1,
        "result_count": 1,
        "missing_db_files": 0,
        "status_counts": {"ok": 1},
        "reason_counts": {},
        "problem_summary": [],
        "results": [
            {
                "action": "NO ACTION",
                "status_label": "OK",
                "reason": None,
                "path": tmp_path / "track.wav",
                "message": "ok",
                "detail": "bad\x00priv\x01payload\x9a",
                "original_size": 0,
                "repaired_size": 0,
                "size_delta": 0,
                "id3_seen": 0,
                "id3_removed": 0,
                "primary_action": None,
                "backup_path": None,
                "mutagen_summary": "PRIV:TRAKTOR4:DMRT\x02\x00\x03",
            }
        ],
    }

    repair.write_xlsx_report(xlsx_path, payload)

    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(xlsx_path) as archive:
        for name in archive.namelist():
            if name.endswith((".xml", ".rels")):
                ET.fromstring(archive.read(name))
        results_xml = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")
    assert "\\x00" in results_xml
    assert "\\x01" in results_xml
    assert "\\x02" in results_xml
    assert "\\x9a" in results_xml


def test_xlsx_report_truncates_text_to_excel_cell_limit(tmp_path: Path) -> None:
    repair = _load_repair_module()
    xlsx_path = tmp_path / "report.xlsx"
    long_summary = "mutagen ok tags=yes keys=" + ("A" * 40000)
    payload = {
        "mode": "dry-run",
        "generated_at": "2026-05-29T12:00:00",
        "source_counts": {"paths": 1, "folders": 0, "databases": 0, "logs": 0},
        "options": {"keep_id3": "first", "workers": 1, "backup_dir": "", "no_backup": False},
        "state": {"enabled": False, "path": None, "skipped_from_state": 0, "skipped_by_reason": 0},
        "total_collected": 1,
        "result_count": 1,
        "missing_db_files": 0,
        "status_counts": {"ok": 1},
        "reason_counts": {},
        "problem_summary": [],
        "results": [
            {
                "action": "NO ACTION",
                "status_label": "OK",
                "reason": None,
                "path": tmp_path / "track.wav",
                "message": "ok",
                "detail": "ok",
                "original_size": 0,
                "repaired_size": 0,
                "size_delta": 0,
                "id3_seen": 0,
                "id3_removed": 0,
                "primary_action": None,
                "backup_path": None,
                "mutagen_summary": long_summary,
            }
        ],
    }

    repair.write_xlsx_report(xlsx_path, payload)

    import xml.etree.ElementTree as ET

    with zipfile.ZipFile(xlsx_path) as archive:
        root = ET.fromstring(archive.read("xl/worksheets/sheet2.xml"))
    namespace = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    values = ["".join(text.text or "" for text in cell.findall(".//m:t", namespace)) for cell in root.findall(".//m:c", namespace)]
    assert max(len(value) for value in values) <= 32767
    assert any("[truncated;" in value for value in values)


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

    first_exit = repair.main(["--folder", str(folder), "--state", str(state_path), "--no-file-log", "--no-report"])
    second.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    second_exit = repair.main(["--folder", str(folder), "--state", str(state_path), "--no-file-log", "--no-report"])

    output = capsys.readouterr().out
    assert first_exit == 0
    assert second_exit == 0
    assert processed == [first, second]
    assert state_path.exists()
    assert "Already checked from state: 1" in output
    assert "Pending tracks: 1" in output


def test_db_mode_collects_existing_tracks_with_root_remap(monkeypatch, tmp_path: Path, capsys) -> None:
    repair = _load_repair_module()
    db_path = tmp_path / "library.sqlite"
    db_root = tmp_path / "db-root"
    file_root = tmp_path / "file-root"
    db_root.mkdir()
    file_root.mkdir()
    existing = file_root / "Album" / "track.wav"
    missing = file_root / "Album" / "missing.wav"
    existing.parent.mkdir()
    existing.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    con = sqlite3.connect(db_path)
    con.execute("create table tracks (id integer primary key, path text not null)")
    con.execute("insert into tracks (path) values (?)", (str(db_root / "Album" / "track.wav"),))
    con.execute("insert into tracks (path) values (?)", (str(db_root / "Album" / "missing.wav"),))
    con.commit()
    con.close()
    processed: list[Path] = []

    def fake_repair_file(path: Path, **_kwargs):
        processed.append(path)
        return repair.FileRepairResult(path=path, status="ok", message="ok")

    monkeypatch.setattr(repair, "repair_file", fake_repair_file)

    exit_code = repair.main(
        [
            "--db",
            str(db_path),
            "--db-root",
            str(db_root),
            "--file-root",
            str(file_root),
            "--no-file-log",
            "--no-report",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert processed == [existing]
    assert "Missing DB files: 1" in output
    assert str(missing) not in output


def test_db_mode_state_skips_checked_files(monkeypatch, tmp_path: Path, capsys) -> None:
    repair = _load_repair_module()
    db_path = tmp_path / "library.sqlite"
    audio_path = tmp_path / "track.wav"
    state_path = tmp_path / "state.json"
    audio_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    con = sqlite3.connect(db_path)
    con.execute("create table tracks (path text not null)")
    con.execute("insert into tracks (path) values (?)", (str(audio_path),))
    con.commit()
    con.close()
    processed: list[Path] = []

    def fake_repair_file(path: Path, **_kwargs):
        processed.append(path)
        return repair.FileRepairResult(path=path, status="ok", message="ok")

    monkeypatch.setattr(repair, "repair_file", fake_repair_file)

    first_exit = repair.main(["--db", str(db_path), "--state", str(state_path), "--no-file-log", "--no-report"])
    second_exit = repair.main(["--db", str(db_path), "--state", str(state_path), "--no-file-log", "--no-report"])

    output = capsys.readouterr().out
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert first_exit == 0
    assert second_exit == 0
    assert processed == [audio_path]
    assert state["sources"] == [f"db:{db_path.resolve()}"]
    assert "Already checked from state: 1" in output
    assert "Pending tracks: 0" in output


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

    first_exit = repair.main(["--folder", str(first_folder), "--no-file-log", "--no-report"])
    repeat_exit = repair.main(["--folder", str(first_folder), "--no-file-log", "--no-report"])
    second_exit = repair.main(["--folder", str(second_folder), "--no-file-log", "--no-report"])

    output = capsys.readouterr().out
    assert first_exit == 0
    assert repeat_exit == 0
    assert second_exit == 0
    assert first_state == repair.resolve_state_path(None, [first_folder])
    assert second_state == repair.resolve_state_path(None, [second_folder])
    assert first_state != second_state
    assert first_state.name.startswith("state.library-a.")
    assert second_state.name.startswith("state.library-b.")
    assert first_state.name.endswith(".json")
    assert first_state.exists()
    assert second_state.exists()
    assert processed == [first_track, second_track]
    assert f"State file: {first_state}" in output
    assert "Already checked from state: 1" in output


def test_default_state_path_uses_safe_folder_label(monkeypatch, tmp_path: Path) -> None:
    repair = _load_repair_module()
    run_dir = tmp_path / "audio_repair"
    monkeypatch.setattr(repair, "DEFAULT_RUN_DIR", run_dir)
    folder = tmp_path / "Library Name #1"
    folder.mkdir()

    state_path = repair.resolve_state_path(None, [folder])

    assert state_path.parent == run_dir
    assert state_path.name.startswith("state.Library_Name_1.")
    assert state_path.name.endswith(".json")


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

    dry_run_exit = repair.main(["--folder", str(folder), "--state", str(state_path), "--no-file-log", "--no-report"])
    apply_exit = repair.main(["--folder", str(folder), "--state", str(state_path), "--no-file-log", "--no-report", "--apply"])
    second_apply_exit = repair.main(
        ["--folder", str(folder), "--state", str(state_path), "--no-file-log", "--no-report", "--apply"]
    )

    assert dry_run_exit == 0
    assert apply_exit == 0
    assert second_apply_exit == 0
    assert calls == [False, True]


def test_state_stores_reason_and_apply_can_filter_by_reason(monkeypatch, tmp_path: Path) -> None:
    repair = _load_repair_module()
    folder = tmp_path / "library"
    folder.mkdir()
    wav_path = folder / "broken.wav"
    aiff_path = folder / "broken.aiff"
    wav_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVE")
    aiff_path.write_bytes(b"FORM\x00\x00\x00\x04AIFF")
    state_path = tmp_path / "state.json"
    calls: list[tuple[Path, bool]] = []
    wanted_reason = "OVERSIZED_DATA"
    monkeypatch.setattr(repair.time, "time", lambda: 1234.9)

    def fake_repair_file(path: Path, *, apply_changes: bool, **_kwargs):
        calls.append((path, apply_changes))
        if path == wav_path:
            return repair.FileRepairResult(
                path=path,
                status="repaired" if apply_changes else "repairable",
                message="ok",
                actions=["shrunk oversized data chunk at offset 36 from declared size 100 to 80"],
            )
        return repair.FileRepairResult(
            path=path,
            status="repairable",
            message="ok",
            actions=["removed empty ID3 chunk at offset 128"],
        )

    monkeypatch.setattr(repair, "repair_file", fake_repair_file)

    dry_run_exit = repair.main(["--folder", str(folder), "--state", str(state_path), "--no-file-log", "--no-report"])
    apply_exit = repair.main(
        [
            "--folder",
            str(folder),
            "--state",
            str(state_path),
            "--no-file-log",
            "--no-report",
            "--apply",
            "--reason",
            "oversized_data",
        ]
    )

    state = json.loads(state_path.read_text(encoding="utf-8"))
    entries = {entry["title"]: entry for entry in state["files"].values()}
    assert dry_run_exit == 0
    assert apply_exit == 0
    assert repair.state_key(wav_path) in state["files"]
    assert str(wav_path.resolve()) not in state["files"]
    assert list(entries["broken.wav"].keys()) == [
        "title",
        "path",
        "size",
        "checked_at",
        "modified_at",
        "mode",
        "message",
        "status",
        "reason",
    ]
    assert isinstance(entries["broken.wav"]["checked_at"], int)
    assert isinstance(entries["broken.wav"]["modified_at"], int)
    assert entries["broken.wav"]["reason"] == wanted_reason
    assert entries["broken.wav"]["mode"] == "apply"
    assert entries["broken.wav"]["message"] == "repair_applied"
    assert entries["broken.wav"]["status"] == "REPAIRED"
    assert entries["broken.aiff"]["reason"] == "EMPTY_ID3"
    assert entries["broken.aiff"]["status"] == "REPAIRABLE"
    assert entries["broken.aiff"]["mode"] == "dry-run"
    assert entries["broken.aiff"]["message"] == "repair_available"
    assert calls == [(aiff_path, False), (wav_path, False), (wav_path, True)]


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
        [
            "--folder",
            str(folder),
            "--workers",
            "2",
            "--state",
            str(tmp_path / "state.json"),
            "--no-file-log",
            "--no-report",
        ]
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
        [
            "--folder",
            str(folder),
            "--workers",
            "4",
            "--apply",
            "--state",
            str(tmp_path / "state.json"),
            "--no-file-log",
            "--no-report",
        ]
    )

    assert exit_code == 0
    assert calls == paths
