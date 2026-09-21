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

from .audio_dedup_bridge import load_audio_dedup_module
from .database import LibraryDatabase
from .db.tracks import canonical_file_path
from .track_models import TrackFileState

REPORT_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
MAX_CACHED_REPORTS = 4
DEFAULT_GROUP_PAGE_LIMIT = 25
MAX_GROUP_PAGE_LIMIT = 200


@dataclass(frozen=True)
class AudioDedupReportSummary:
    report_id: str
    generated_at: str
    search_mode: str
    group_count: int
    candidate_count: int
    fake_bitrate_candidate_count: int
    fingerprint_min_similarity: float | None
    fingerprint_confidence_high: float | None
    fingerprint_confidence_medium: float | None
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
    effective_source_rate_hz: float | None
    suspected_transcode: bool | None
    spectral_note: str | None
    fingerprint_vs_keeper: float | None
    reasons: list[str] = field(default_factory=list)
    review_reasons: list[str] = field(default_factory=list)
    stale: bool = False
    stale_reason: str | None = None
    playable: bool = False


@dataclass(frozen=True)
class AudioDedupPair:
    left_track_id: int
    right_track_id: int
    fingerprint_similarity: float | None
    duration_diff_seconds: float | None
    duration_diff_ratio: float | None
    candidate_sources: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AudioDedupGroup:
    group_id: int
    confidence: str
    fingerprint_similarity: float | None
    suspected_transcode_count: int
    upsampled_file_count: int
    stale_file_count: int
    files: list[AudioDedupFile] = field(default_factory=list)
    pairs: list[AudioDedupPair] = field(default_factory=list)
    review_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AudioDedupGroupPage:
    report_id: str
    search_mode: str
    generated_at: str
    total_groups: int
    filtered_groups: int
    # Copies the current path filter selects across the whole report, not just
    # this page: the review shows it so a filter like "mp3" reveals its reach
    # before anything is marked.
    filtered_copies: int
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
    report_dir = (resolved_dir / report_id).resolve(strict=False)
    if report_dir.parent != resolved_dir:
        raise ValueError(f"Invalid report id: {report_id}")
    candidate = report_dir / f"{report_id}.json"
    if not candidate.is_file():
        raise KeyError(f"Unknown audio dedup report: {report_id}")
    return candidate


def report_xlsx_path(out_dir: Path, report_id: str) -> Path:
    json_path = report_json_path(out_dir, report_id)
    xlsx_path = json_path.with_suffix(".xlsx")
    if not xlsx_path.is_file():
        raise KeyError(f"Audio dedup report has no workbook: {report_id}")
    return xlsx_path


def delete_report(out_dir: Path, report_id: str) -> list[str]:
    """Remove one report and whatever it wrote beside its JSON.

    A report is disposable output: the scan can be run again, and nothing here
    touches audio files or database rows. The id is resolved through
    report_json_path, so only a file inside the report directory can be removed.
    """
    json_path = report_json_path(out_dir, report_id)
    removed: list[str] = []
    for path in (json_path, json_path.with_suffix(".xlsx"), json_path.with_suffix(".log")):
        if path.is_file():
            path.unlink()
            removed.append(path.name)
    report_dir = json_path.parent
    # The directory goes only once it is empty. Whatever else was put in there
    # is not part of the report and is not ours to remove.
    if not any(report_dir.iterdir()):
        report_dir.rmdir()
    return removed


def load_report_payload(out_dir: Path, report_id: str) -> dict:
    return _CACHE.load(report_json_path(out_dir, report_id))


def list_reports(out_dir: Path) -> list[AudioDedupReportSummary]:
    resolved_dir = Path(out_dir).expanduser().resolve(strict=False)
    if not resolved_dir.is_dir():
        return []
    summaries: list[AudioDedupReportSummary] = []
    for json_path in sorted(resolved_dir.glob("*/*.json")):
        # A report is its directory: the id names both, and anything else that
        # ends up in there is not a report of ours to list.
        if json_path.stem != json_path.parent.name:
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


def _confidence_bands(payload: dict) -> tuple[float | None, float | None]:
    """The fingerprint bands a report's confidence levels stand for.

    A run records its own bands. Reports written before it did are still read
    with the same rule below, so they get the bands in force now rather than
    leaving the review with levels it cannot explain.
    """
    retrieval = _mapping(payload.get('fingerprint_retrieval'))
    high = _float_or_none(retrieval.get('fingerprint_confidence_high'))
    medium = _float_or_none(retrieval.get('fingerprint_confidence_medium'))
    if high is not None and medium is not None:
        return high, medium
    config_module = load_audio_dedup_module('config')
    return (
        float(config_module.FINGERPRINT_CONFIDENCE_HIGH),
        float(config_module.FINGERPRINT_CONFIDENCE_MEDIUM),
    )


def _resolved_confidence(group: dict) -> str:
    """The confidence the review shows for one group.

    The fingerprint decides it, and deriving it here means a report written
    before that rule reads the same way as one written after, instead of the
    level depending on the day its scan ran.
    """
    keeper_module = load_audio_dedup_module('keeper')
    scores = [
        _float_or_none(entry.get('fingerprint_similarity'))
        for entry in _entries(group, 'pairwise_evidence')
    ]
    best = max((score for score in scores if score is not None), default=None)
    return str(keeper_module.fingerprint_confidence_category(best))


def _summary(json_path: Path, payload: dict) -> AudioDedupReportSummary:
    statistics = _mapping(payload.get("statistics"))
    return AudioDedupReportSummary(
        report_id=json_path.stem,
        generated_at=str(payload.get("generated_at", "")),
        search_mode=str(payload.get("search_mode", "")),
        group_count=_int(payload.get("group_count")),
        candidate_count=_int(statistics.get("candidate_count")),
        fake_bitrate_candidate_count=_int(statistics.get("fake_bitrate_candidate_count")),
        # The run's own fingerprint boundary, which the search mode decides. The
        # review filters by it instead of asking the reviewer for a number.
        fingerprint_min_similarity=_float_or_none(
            _mapping(payload.get("fingerprint_retrieval")).get("fingerprint_review_min_similarity")
        ),
        # Present only where confidence is read from the fingerprint, which is
        # what lets the review show the band behind a confidence level.
        fingerprint_confidence_high=_confidence_bands(payload)[0],
        fingerprint_confidence_medium=_confidence_bands(payload)[1],
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
    path_filter = path_filter_key(path_contains)
    resolved = [(group, _resolved_confidence(group)) for group in raw_groups]
    matching = [
        (group, group_confidence)
        for group, group_confidence in resolved
        if _group_matches(
            group,
            group_confidence=group_confidence,
            confidence=confidence,
            min_fingerprint=min_fingerprint,
            fake_bitrate_only=fake_bitrate_only,
            path_filter=path_filter,
        )
    ]
    matching = _groups_still_worth_reviewing(database, matching)
    # Reviewing means walking a folder, so the pages run in path order. A
    # report written before that rule is ordered here rather than left
    # scattered across the list.
    matching.sort(key=lambda item: _group_path_key(item[0]))
    selected_limit = max(1, min(int(limit), MAX_GROUP_PAGE_LIMIT))
    selected_offset = max(0, int(offset))
    window = matching[selected_offset : selected_offset + selected_limit]
    live_states = _file_states(database, _window_track_ids([group for group, _ in window]))
    return AudioDedupGroupPage(
        report_id=report_id,
        search_mode=str(payload.get("search_mode", "")),
        generated_at=str(payload.get("generated_at", "")),
        total_groups=len(raw_groups),
        filtered_groups=len(matching),
        filtered_copies=sum(len(_members(group)) for group, _ in matching),
        offset=selected_offset,
        limit=selected_limit,
        groups=[
            _group(group, live_states, confidence=group_confidence)
            for group, group_confidence in window
        ],
    )


def path_filter_key(text: str) -> str:
    """One reading of the reviewer's path filter, shared by review and delete.

    Stored paths are POSIX and compared case-insensitively, so typing
    ``M:\\Volumes\\Abstracted``, ``Volumes/Abstracted`` or ``Abstracted`` selects
    the same copies. Matching is containment, not a resolved folder: the
    reviewer types the branch they mean.
    """
    return str(text).strip().replace("\\", "/").lower()


def _group_inside_filter(group: dict, path_filter: str) -> bool:
    """Whether every copy of this group lives under the filter."""
    members = _members(group)
    return bool(members) and all(
        path_filter in str(entry.get("path", "")).replace("\\", "/").lower()
        for entry in members
    )


def _groups_still_worth_reviewing(
    database: LibraryDatabase,
    matching: list[tuple[dict, str]],
) -> list[tuple[dict, str]]:
    """Drop the groups a deletion already settled.

    A report is a record of the run, not of the library, so it keeps naming
    copies that have since been deleted. A group down to one surviving track
    has nothing left to decide, and leaving it in the list only pads the pages
    and the counts. Only the database is consulted here: whether each file is
    still on disk costs a stat per copy and is answered for the visible page.
    """
    track_ids = [
        _int(entry.get("track_id"), default=-1)
        for group, _ in matching
        for entry in _members(group)
    ]
    live = database.existing_track_ids([track_id for track_id in track_ids if track_id > 0])
    return [
        (group, group_confidence)
        for group, group_confidence in matching
        if sum(
            1
            for entry in _members(group)
            if _int(entry.get("track_id"), default=-1) in live
        )
        >= 2
    ]


def _group_path_key(group: dict) -> str:
    """Where a group sits in the list: the earliest path it holds."""
    paths = [
        str(entry.get("path", "")).replace("\\", "/").lower()
        for entry in _members(group)
    ]
    return min(paths) if paths else ""


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


def _group(
    group: dict,
    live_states: dict[int, TrackFileState],
    *,
    confidence: str,
) -> AudioDedupGroup:
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
        confidence=confidence,
        fingerprint_similarity=max(fingerprint_scores) if fingerprint_scores else None,
        suspected_transcode_count=sum(1 for item in files if item.suspected_transcode),
        upsampled_file_count=sum(
            1 for item in files if item.effective_source_rate_hz is not None
        ),
        stale_file_count=sum(1 for item in files if item.stale),
        files=files,
        pairs=pairs,
        review_reasons=_strings(group.get("review_reasons")),
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
    reasons = _strings(keeper.get("why_keep")) if is_keeper else []
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
        effective_source_rate_hz=_float_or_none(entry.get("effective_source_rate_hz")),
        suspected_transcode=(
            bool(entry["suspected_transcode"]) if entry.get("suspected_transcode") is not None else None
        ),
        spectral_note=_text_or_none(entry.get("spectral_note")),
        fingerprint_vs_keeper=_float_or_none(source.get("fingerprint_vs_keeper")),
        reasons=reasons,
        review_reasons=_strings(source.get("review_reasons")),
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
        left_track_id=_int(entry.get('left_track_id')),
        right_track_id=_int(entry.get('right_track_id')),
        fingerprint_similarity=_float_or_none(entry.get('fingerprint_similarity')),
        duration_diff_seconds=_float_or_none(entry.get('duration_diff_seconds')),
        duration_diff_ratio=_float_or_none(entry.get('duration_diff_ratio')),
        candidate_sources=_strings(entry.get('candidate_sources')),
    )


def _group_matches(
    group: dict,
    *,
    group_confidence: str,
    confidence: tuple[str, ...],
    min_fingerprint: float | None,
    fake_bitrate_only: bool,
    path_filter: str,
) -> bool:
    if confidence and group_confidence not in confidence:
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
    # The filter keeps whole groups: every copy of the group has to live under
    # it. A group split across the filter is not the reviewer's to settle here,
    # and half of it on screen has nothing to compare against.
    if path_filter and not _group_inside_filter(group, path_filter):
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
