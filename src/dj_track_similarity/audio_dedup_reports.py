"""Read Audio Dedup report artifacts for review in the UI.

A scan writes JSON, XLSX, and log files and those stay the record of the run, so
review reads them back rather than holding a run in process memory. A full
library report is several megabytes and thousands of groups, which is a long
review session: keeping it on disk lets a review survive a server restart and
lets the UI open a report produced by the CLI.

Every file of a group is checked against the live database and the disk with the
same tests the apply gate runs later. A reviewer then sees a stale candidate
before confirming instead of discovering it in the skipped list afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import threading

from .database import LibraryDatabase
from .db_tracks import canonical_file_path
from .track_models import TrackFileState

REPORT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
MAX_CACHED_REPORTS = 4
DEFAULT_GROUP_PAGE_LIMIT = 25
MAX_GROUP_PAGE_LIMIT = 200


@dataclass(frozen=True)
class AudioDedupReportSummary:
    report_id: str
    generated_at: str
    root: str
    search_mode: str
    preset: str
    mode: str
    group_count: int
    candidate_count: int
    safe_candidate_count: int
    review_candidate_count: int
    fake_bitrate_candidate_count: int
    database_path: str | None
    modified_at: float
    has_xlsx: bool


@dataclass(frozen=True)
class AudioDedupFile:
    track_id: int
    role: str
    path: str
    file_name: str
    artist: str | None
    title: str | None
    album: str | None
    duration: float | None
    bpm: float | None
    musical_key: str | None
    size: int
    audio_format: str
    size_per_second: float | None
    metadata_completeness: int | None
    bit_rate_bps: int | None
    sample_rate_hz: int | None
    bit_depth: int | None
    true_peak_dbtp: float | None
    dynamic_range_db: float | None
    loudness_range_lu: float | None
    spectral_cutoff_hz: float | None
    spectral_sharpness_db: float | None
    suspected_transcode: bool
    spectral_note: str | None
    score_vs_keeper: float | None
    safe_to_delete: bool
    reasons: list[str] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)
    stale: bool = False
    stale_reason: str | None = None
    playable: bool = False


@dataclass(frozen=True)
class AudioDedupPair:
    left_track_id: int
    right_track_id: int
    score: float | None
    fingerprint_similarity: float | None
    sonara_similarity: float | None
    mert_similarity: float | None
    maest_similarity: float | None
    muq_similarity: float | None
    clap_similarity: float | None
    content_similarity: float | None
    duration_diff_seconds: float | None
    duration_diff_ratio: float | None
    candidate_sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AudioDedupGroup:
    group_id: int
    confidence: str
    score: float | None
    fingerprint_similarity: float | None
    suspected_transcode_count: int
    stale_file_count: int
    files: list[AudioDedupFile] = field(default_factory=list)
    pairs: list[AudioDedupPair] = field(default_factory=list)
    blocked_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AudioDedupGroupPage:
    report_id: str
    root: str
    search_mode: str
    generated_at: str
    total_groups: int
    filtered_groups: int
    offset: int
    limit: int
    groups: list[AudioDedupGroup] = field(default_factory=list)


class _ReportCache:
    """Parsed reports keyed by their identity on disk.

    A full library report is megabytes of JSON and every page request would
    otherwise reparse it.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, int, dict]] = {}

    def load(self, path: Path) -> dict:
        stats = path.stat()
        key = str(path)
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None and cached[0] == stats.st_mtime and cached[1] == stats.st_size:
                return cached[2]
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Audio dedup report is not an object: {path.name}")
        with self._lock:
            if len(self._entries) >= MAX_CACHED_REPORTS:
                self._entries.pop(next(iter(self._entries)))
            self._entries[key] = (stats.st_mtime, stats.st_size, payload)
        return payload

_CACHE = _ReportCache()


def report_json_path(out_dir: Path, report_id: str) -> Path:
    """Resolve one report by id, refusing anything that escapes the report directory."""
    if not REPORT_ID_PATTERN.match(report_id):
        raise ValueError(f"Invalid report id: {report_id}")
    resolved_dir = Path(out_dir).expanduser().resolve(strict=False)
    candidate = (resolved_dir / f"{report_id}.json").resolve(strict=False)
    if candidate.parent != resolved_dir:
        raise ValueError(f"Invalid report id: {report_id}")
    if not candidate.is_file():
        raise KeyError(f"Unknown audio dedup report: {report_id}")
    return candidate


def report_xlsx_path(out_dir: Path, report_id: str) -> Path:
    json_path = report_json_path(out_dir, report_id)
    xlsx_path = json_path.with_suffix(".xlsx")
    if not xlsx_path.is_file():
        raise KeyError(f"Audio dedup report has no workbook: {report_id}")
    return xlsx_path


def load_report_payload(out_dir: Path, report_id: str) -> dict:
    return _CACHE.load(report_json_path(out_dir, report_id))


def list_reports(out_dir: Path) -> list[AudioDedupReportSummary]:
    resolved_dir = Path(out_dir).expanduser().resolve(strict=False)
    if not resolved_dir.is_dir():
        return []
    summaries: list[AudioDedupReportSummary] = []
    for json_path in sorted(resolved_dir.glob("*.json")):
        if json_path.name.startswith("~"):
            continue
        try:
            payload = _CACHE.load(json_path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if "groups" not in payload:
            continue
        summaries.append(_summary(json_path, payload))
    summaries.sort(key=lambda summary: summary.modified_at, reverse=True)
    return summaries


def _summary(json_path: Path, payload: dict) -> AudioDedupReportSummary:
    statistics = _mapping(payload.get("statistics"))
    return AudioDedupReportSummary(
        report_id=json_path.stem,
        generated_at=str(payload.get("generated_at", "")),
        root=str(payload.get("root", "")),
        search_mode=str(payload.get("search_mode", "")),
        preset=str(payload.get("preset", "")),
        mode=str(payload.get("mode", "")),
        group_count=_int(payload.get("group_count")),
        candidate_count=_int(statistics.get("candidate_count")),
        safe_candidate_count=_int(statistics.get("safe_candidate_count")),
        review_candidate_count=_int(statistics.get("review_candidate_count")),
        fake_bitrate_candidate_count=_int(statistics.get("fake_bitrate_candidate_count")),
        database_path=_text_or_none(payload.get("database_path")),
        modified_at=json_path.stat().st_mtime,
        has_xlsx=json_path.with_suffix(".xlsx").is_file(),
    )


def report_summary(out_dir: Path, report_id: str) -> AudioDedupReportSummary:
    json_path = report_json_path(out_dir, report_id)
    return _summary(json_path, _CACHE.load(json_path))


def group_page(
    payload: dict,
    *,
    database: LibraryDatabase,
    report_id: str,
    offset: int = 0,
    limit: int = DEFAULT_GROUP_PAGE_LIMIT,
    confidence: tuple[str, ...] = (),
    min_fingerprint: float | None = None,
    fake_bitrate_only: bool = False,
    path_contains: str = "",
) -> AudioDedupGroupPage:
    raw_groups = _groups(payload)
    matching = [
        group
        for group in raw_groups
        if _group_matches(
            group,
            confidence=confidence,
            min_fingerprint=min_fingerprint,
            fake_bitrate_only=fake_bitrate_only,
            path_contains=path_contains.strip().lower(),
        )
    ]
    selected_limit = max(1, min(int(limit), MAX_GROUP_PAGE_LIMIT))
    selected_offset = max(0, int(offset))
    window = matching[selected_offset : selected_offset + selected_limit]
    live_states = _file_states(database, _window_track_ids(window))
    return AudioDedupGroupPage(
        report_id=report_id,
        root=str(payload.get("root", "")),
        search_mode=str(payload.get("search_mode", "")),
        generated_at=str(payload.get("generated_at", "")),
        total_groups=len(raw_groups),
        filtered_groups=len(matching),
        offset=selected_offset,
        limit=selected_limit,
        groups=[_group(group, live_states) for group in window],
    )


def _window_track_ids(groups: list[dict]) -> list[int]:
    track_ids: list[int] = []
    for group in groups:
        for entry in _members(group):
            track_id = _int(entry.get("track_id"), default=-1)
            if track_id > 0:
                track_ids.append(track_id)
    return track_ids


def _file_states(
    database: LibraryDatabase,
    track_ids: list[int],
) -> dict[int, TrackFileState]:
    """Live identity and file facts, tolerating ids the library no longer holds.

    A report outlives the rows it describes: a confirmed delete removes them.
    The bulk read fails closed on an unknown id, so fall back to single reads
    only when that happens rather than paying for them on every page.
    """
    unique_ids = sorted(set(track_ids))
    if not unique_ids:
        return {}
    try:
        states = database.get_track_file_states_by_ids(unique_ids, include_missing=True)
        return {state.track_id: state for state in states}
    except (KeyError, ValueError):
        pass
    resolved: dict[int, TrackFileState] = {}
    for track_id in unique_ids:
        try:
            state = database.get_track_file_states_by_ids((track_id,), include_missing=True)[0]
        except (IndexError, KeyError, ValueError):
            continue
        resolved[track_id] = state
    return resolved


def _group(group: dict, live_states: dict[int, TrackFileState]) -> AudioDedupGroup:
    keeper = _mapping(group.get("suggested_keeper"))
    keeper_id = _int(keeper.get("track_id"), default=-1)
    candidates = {
        _int(entry.get("track_id"), default=-1): entry
        for entry in _entries(group, "candidate_deletes")
    }
    files = [
        _file(entry, keeper=keeper, candidate=candidates.get(_int(entry.get("track_id"), default=-1)), keeper_id=keeper_id, live_states=live_states)
        for entry in _members(group)
    ]
    pairs = [_pair(entry) for entry in _entries(group, "pairwise_evidence")]
    fingerprint_scores = [
        pair.fingerprint_similarity for pair in pairs if pair.fingerprint_similarity is not None
    ]
    return AudioDedupGroup(
        group_id=_int(group.get("group_id")),
        confidence=str(group.get("confidence", "")),
        score=_float_or_none(group.get("score")),
        fingerprint_similarity=max(fingerprint_scores) if fingerprint_scores else None,
        suspected_transcode_count=sum(1 for item in files if item.suspected_transcode),
        stale_file_count=sum(1 for item in files if item.stale),
        files=files,
        pairs=pairs,
        blocked_reasons=_strings(group.get("blocked_reasons")),
    )


def _file(
    entry: dict,
    *,
    keeper: dict,
    candidate: dict | None,
    keeper_id: int,
    live_states: dict[int, TrackFileState],
) -> AudioDedupFile:
    track_id = _int(entry.get("track_id"), default=-1)
    path_text = str(entry.get("path", ""))
    is_keeper = track_id == keeper_id
    source = candidate if candidate is not None else entry
    reasons = _strings(keeper.get("why_keep")) if is_keeper else _strings(source.get("why_delete_or_review"))
    stale_reason = _stale_reason(entry, live_states.get(track_id))
    state = live_states.get(track_id)
    return AudioDedupFile(
        track_id=track_id,
        role="keeper" if is_keeper else "duplicate",
        path=path_text,
        file_name=Path(path_text).name,
        artist=_text_or_none(entry.get("artist")),
        title=_text_or_none(entry.get("title")),
        album=_text_or_none(entry.get("album")),
        duration=_float_or_none(entry.get("duration")),
        bpm=_float_or_none(entry.get("bpm")),
        musical_key=_text_or_none(entry.get("musical_key")),
        size=_int(entry.get("size")),
        audio_format=Path(path_text).suffix.lstrip(".").upper(),
        size_per_second=_float_or_none(entry.get("size_per_second")),
        metadata_completeness=_int_or_none(entry.get("metadata_completeness")),
        bit_rate_bps=_int_or_none(entry.get("bit_rate_bps")),
        sample_rate_hz=_int_or_none(entry.get("sample_rate_hz")),
        bit_depth=_int_or_none(entry.get("bit_depth")),
        true_peak_dbtp=_float_or_none(entry.get("true_peak_dbtp")),
        dynamic_range_db=_float_or_none(entry.get("dynamic_range_db")),
        loudness_range_lu=_float_or_none(entry.get("loudness_range_lu")),
        spectral_cutoff_hz=_float_or_none(entry.get("spectral_cutoff_hz")),
        spectral_sharpness_db=_float_or_none(entry.get("spectral_sharpness_db")),
        suspected_transcode=bool(entry.get("suspected_transcode", False)),
        spectral_note=_text_or_none(entry.get("spectral_note")),
        score_vs_keeper=_float_or_none(source.get("score_vs_keeper")),
        safe_to_delete=source.get("safe_to_delete") == "true_candidate",
        reasons=reasons,
        blocked_reasons=_strings(source.get("blocked_reasons")),
        stale=stale_reason is not None,
        stale_reason=stale_reason,
        # A stale copy is still worth hearing, so playability is judged on its
        # own terms: exactly what /media/{track_id} needs to serve the file.
        playable=(
            state is not None
            and state.missing_since is None
            and bool(path_text)
            and Path(path_text).is_file()
        ),
    )


def _stale_reason(entry: dict, state: TrackFileState | None) -> str | None:
    """Why this reported file would be refused by the apply gate, if it would.

    These are the checks ``apply_duplicate_deletions`` repeats before deleting.
    """
    path_text = str(entry.get("path", ""))
    if state is None:
        return "track is no longer in the library"
    if (
        state.catalog_uuid != str(entry.get("catalog_uuid", ""))
        or state.track_uuid != str(entry.get("track_uuid", ""))
        or canonical_file_path(state.file_path) != canonical_file_path(path_text)
    ):
        return "report identity is stale"
    try:
        reported_size = int(entry["size"])
        reported_modified_ns = int(entry["file_modified_ns"])
    except (KeyError, TypeError, ValueError):
        return "report file facts are missing"
    if state.file_size_bytes != reported_size or state.file_modified_ns != reported_modified_ns:
        return "report file facts are stale"
    if not path_text or not Path(path_text).is_file():
        return "file is missing on disk"
    return None


def _pair(entry: dict) -> AudioDedupPair:
    return AudioDedupPair(
        left_track_id=_int(entry.get("left_track_id")),
        right_track_id=_int(entry.get("right_track_id")),
        score=_float_or_none(entry.get("score")),
        fingerprint_similarity=_float_or_none(entry.get("fingerprint_similarity")),
        sonara_similarity=_float_or_none(entry.get("sonara_similarity")),
        mert_similarity=_float_or_none(entry.get("mert_similarity")),
        maest_similarity=_float_or_none(entry.get("maest_similarity")),
        muq_similarity=_float_or_none(entry.get("muq_similarity")),
        clap_similarity=_float_or_none(entry.get("clap_similarity")),
        content_similarity=_float_or_none(entry.get("content_similarity")),
        duration_diff_seconds=_float_or_none(entry.get("duration_diff_seconds")),
        duration_diff_ratio=_float_or_none(entry.get("duration_diff_ratio")),
        candidate_sources=_strings(entry.get("candidate_sources")),
    )


def _group_matches(
    group: dict,
    *,
    confidence: tuple[str, ...],
    min_fingerprint: float | None,
    fake_bitrate_only: bool,
    path_contains: str,
) -> bool:
    if confidence and str(group.get("confidence", "")) not in confidence:
        return False
    if fake_bitrate_only and not any(
        bool(entry.get("suspected_transcode", False)) for entry in _members(group)
    ):
        return False
    if min_fingerprint is not None:
        scores = [
            _float_or_none(entry.get("fingerprint_similarity"))
            for entry in _entries(group, "pairwise_evidence")
        ]
        best = max((score for score in scores if score is not None), default=None)
        if best is None or best < min_fingerprint:
            return False
    if path_contains and not any(
        path_contains in str(entry.get("path", "")).lower() for entry in _members(group)
    ):
        return False
    return True


def _groups(payload: dict) -> list[dict]:
    return _entries(payload, "groups")


def _entries(container: dict, field_name: str) -> list[dict]:
    entries = container.get(field_name, [])
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def _members(group: dict) -> list[dict]:
    members = _entries(group, "tracks")
    if members:
        return members
    keeper = group.get("suggested_keeper")
    fallback = [keeper] if isinstance(keeper, dict) else []
    return fallback + _entries(group, "candidate_deletes")


def _mapping(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _int(value: object, *, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
