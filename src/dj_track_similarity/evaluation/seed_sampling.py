from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math
from pathlib import Path
import random
from typing import TYPE_CHECKING

from .csv_io import CsvRow, write_csv_rows

if TYPE_CHECKING:
    from ..database import LibraryDatabase


SEED_SAMPLE_COLUMNS = (
    "track_id",
    "artist",
    "title",
    "album",
    "bpm",
    "musical_key",
    "energy",
    "has_sonara_analysis",
    "has_mert_embedding",
    "has_clap_embedding",
    "has_maest_embedding",
    "bucket",
)


@dataclass(frozen=True)
class SeedSampleTrack:
    track_id: int
    artist: str | None
    title: str | None
    album: str | None
    bpm: float | None
    musical_key: str | None
    energy: float | None
    has_sonara_analysis: bool
    has_mert_embedding: bool
    has_clap_embedding: bool
    has_maest_embedding: bool
    bucket: str

    @property
    def known_artist_key(self) -> str | None:
        if self.artist is None:
            return None
        normalized = " ".join(self.artist.casefold().split())
        return normalized or None

    @property
    def has_bucketable_bpm_and_energy(self) -> bool:
        return _finite_positive_number(self.bpm) and _finite_number(self.energy)

    def csv_row(self) -> CsvRow:
        return {
            "track_id": self.track_id,
            "artist": _optional_text(self.artist),
            "title": _optional_text(self.title),
            "album": _optional_text(self.album),
            "bpm": _optional_number(self.bpm),
            "musical_key": _optional_text(self.musical_key),
            "energy": _optional_number(self.energy),
            "has_sonara_analysis": _analysis_flag(self.has_sonara_analysis),
            "has_mert_embedding": _analysis_flag(self.has_mert_embedding),
            "has_clap_embedding": _analysis_flag(self.has_clap_embedding),
            "has_maest_embedding": _analysis_flag(self.has_maest_embedding),
            "bucket": self.bucket,
        }


@dataclass(frozen=True)
class SeedSampleResult:
    rows: tuple[SeedSampleTrack, ...]
    eligible_count: int
    buckets_used: tuple[str, ...]
    bucket_mode: str

    @property
    def selected_count(self) -> int:
        return len(self.rows)


def export_seed_sample(
    db: LibraryDatabase,
    *,
    count: int = 50,
    random_seed: int = 123,
    require_complete_analysis: bool = True,
) -> SeedSampleResult:
    clean_count = _positive_int(count, "count")
    clean_random_seed = _int_value(random_seed, "random_seed")
    eligible_tracks = load_seed_sample_eligible_tracks(db, require_complete_analysis=require_complete_analysis)
    selected_tracks, bucket_mode = sample_seed_tracks(
        eligible_tracks,
        count=clean_count,
        random_seed=clean_random_seed,
    )
    return SeedSampleResult(
        rows=selected_tracks,
        eligible_count=len(eligible_tracks),
        buckets_used=_buckets_used(selected_tracks),
        bucket_mode=bucket_mode,
    )


def load_seed_sample_eligible_tracks(
    db: LibraryDatabase,
    *,
    require_complete_analysis: bool = True,
) -> tuple[SeedSampleTrack, ...]:
    where_sql = _complete_analysis_where_sql() if require_complete_analysis else ""
    with db.connect() as connection:
        rows = connection.execute(
            f"""
            SELECT id, artist, title, album, bpm, musical_key, energy,
                   has_sonara_analysis, has_mert_embedding, has_clap_embedding, has_maest_embedding
            FROM tracks
            {where_sql}
            ORDER BY id
            """,
        ).fetchall()
    return tuple(_row_to_seed_sample_track(row) for row in rows)


def sample_seed_tracks(
    tracks: Sequence[SeedSampleTrack],
    *,
    count: int,
    random_seed: int,
) -> tuple[tuple[SeedSampleTrack, ...], str]:
    clean_count = _positive_int(count, "count")
    if not tracks:
        return (), "random"

    target_count = min(clean_count, len(tracks))
    rng = random.Random(_int_value(random_seed, "random_seed"))
    if _has_enough_bucket_data(tracks, target_count):
        return _stratified_seed_tracks(tracks, target_count, rng), "stratified"
    return _random_seed_tracks(tracks, target_count, rng), "random"


def write_seed_sample_csv(path: str | Path, rows: Sequence[SeedSampleTrack]) -> None:
    write_csv_rows(path, SEED_SAMPLE_COLUMNS, rows)


def _complete_analysis_where_sql() -> str:
    return """
            WHERE has_sonara_analysis = 1
              AND has_mert_embedding = 1
              AND has_clap_embedding = 1
              AND has_maest_embedding = 1
            """


def _row_to_seed_sample_track(row: Mapping[str, object]) -> SeedSampleTrack:
    bpm = _optional_float(row["bpm"])
    energy = _optional_float(row["energy"])
    return SeedSampleTrack(
        track_id=int(row["id"]),
        artist=_optional_text_or_none(row["artist"]),
        title=_optional_text_or_none(row["title"]),
        album=_optional_text_or_none(row["album"]),
        bpm=bpm,
        musical_key=_optional_text_or_none(row["musical_key"]),
        energy=energy,
        has_sonara_analysis=bool(row["has_sonara_analysis"]),
        has_mert_embedding=bool(row["has_mert_embedding"]),
        has_clap_embedding=bool(row["has_clap_embedding"]),
        has_maest_embedding=bool(row["has_maest_embedding"]),
        bucket=_bucket_for_values(bpm, energy),
    )


def _has_enough_bucket_data(tracks: Sequence[SeedSampleTrack], target_count: int) -> bool:
    if target_count <= 1:
        return False
    real_buckets = {track.bucket for track in tracks if track.has_bucketable_bpm_and_energy}
    bucketable_count = sum(1 for track in tracks if track.has_bucketable_bpm_and_energy)
    return len(real_buckets) >= 2 and bucketable_count >= target_count


def _stratified_seed_tracks(
    tracks: Sequence[SeedSampleTrack],
    target_count: int,
    rng: random.Random,
) -> tuple[SeedSampleTrack, ...]:
    tracks_by_bucket = _shuffled_tracks_by_bucket(tracks, rng)
    bucket_order = list(tracks_by_bucket)
    rng.shuffle(bucket_order)
    candidate_order = _round_robin_bucket_tracks(tracks_by_bucket, bucket_order)
    return _prefer_distinct_known_artists(candidate_order, target_count)


def _random_seed_tracks(
    tracks: Sequence[SeedSampleTrack],
    target_count: int,
    rng: random.Random,
) -> tuple[SeedSampleTrack, ...]:
    candidate_order = list(sorted(tracks, key=lambda track: track.track_id))
    rng.shuffle(candidate_order)
    return _prefer_distinct_known_artists(candidate_order, target_count)


def _shuffled_tracks_by_bucket(
    tracks: Sequence[SeedSampleTrack],
    rng: random.Random,
) -> dict[str, list[SeedSampleTrack]]:
    tracks_by_bucket: dict[str, list[SeedSampleTrack]] = {}
    for track in sorted(tracks, key=lambda candidate: candidate.track_id):
        tracks_by_bucket.setdefault(track.bucket, []).append(track)
    for bucket_tracks in tracks_by_bucket.values():
        rng.shuffle(bucket_tracks)
    return dict(sorted(tracks_by_bucket.items()))


def _round_robin_bucket_tracks(
    tracks_by_bucket: Mapping[str, Sequence[SeedSampleTrack]],
    bucket_order: Sequence[str],
) -> tuple[SeedSampleTrack, ...]:
    indexes = {bucket: 0 for bucket in bucket_order}
    ordered_tracks: list[SeedSampleTrack] = []
    while True:
        added_this_round = False
        for bucket in bucket_order:
            bucket_tracks = tracks_by_bucket[bucket]
            index = indexes[bucket]
            if index >= len(bucket_tracks):
                continue
            ordered_tracks.append(bucket_tracks[index])
            indexes[bucket] = index + 1
            added_this_round = True
        if not added_this_round:
            return tuple(ordered_tracks)


def _prefer_distinct_known_artists(
    candidate_order: Sequence[SeedSampleTrack],
    target_count: int,
) -> tuple[SeedSampleTrack, ...]:
    selected: list[SeedSampleTrack] = []
    skipped_duplicates: list[SeedSampleTrack] = []
    used_artist_keys: set[str] = set()
    for track in candidate_order:
        if len(selected) >= target_count:
            break
        artist_key = track.known_artist_key
        if artist_key is not None and artist_key in used_artist_keys:
            skipped_duplicates.append(track)
            continue
        selected.append(track)
        if artist_key is not None:
            used_artist_keys.add(artist_key)

    if len(selected) >= target_count:
        return tuple(selected)

    for track in skipped_duplicates:
        if len(selected) >= target_count:
            break
        selected.append(track)
    return tuple(selected)


def _buckets_used(tracks: Sequence[SeedSampleTrack]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(track.bucket for track in tracks))


def _bucket_for_values(bpm: float | None, energy: float | None) -> str:
    return f"{_bpm_bucket(bpm)}__{_energy_bucket(energy)}"


def _bpm_bucket(bpm: float | None) -> str:
    if not _finite_positive_number(bpm):
        return "bpm_unknown"
    bucket_start = int(float(bpm) // 10 * 10)
    return f"bpm_{bucket_start:03d}_{bucket_start + 9:03d}"


def _energy_bucket(energy: float | None) -> str:
    if not _finite_number(energy):
        return "energy_unknown"
    clean_energy = float(energy)
    if clean_energy < 0.33:
        return "energy_low"
    if clean_energy < 0.66:
        return "energy_mid"
    return "energy_high"


def _positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be a positive integer")
    try:
        clean_value = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a positive integer") from error
    if clean_value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return clean_value


def _int_value(value: int, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} must be an integer")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be an integer") from error


def _optional_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _optional_text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_number(value: object) -> str:
    if value is None:
        return ""
    return str(float(value))


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    clean_value = float(value)
    if not math.isfinite(clean_value):
        return None
    return clean_value


def _analysis_flag(value: bool) -> int:
    return 1 if value else 0


def _finite_positive_number(value: float | None) -> bool:
    return value is not None and math.isfinite(float(value)) and float(value) > 0


def _finite_number(value: float | None) -> bool:
    return value is not None and math.isfinite(float(value))
