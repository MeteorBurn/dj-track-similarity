from __future__ import annotations

from collections.abc import Iterable
import hashlib
from io import BytesIO

from . import config as config_module
from . import models as models_module
from . import result_formatting as result_formatting_module
from . import text_safety as text_safety_module


def repair_wave_bytes(data: bytes, *, keep_id3: str = "first") -> models_module.ByteRepairResult:
    if keep_id3 not in {"first", "last", "none"}:
        raise models_module.RepairError(f"Unsupported keep-id3 mode: {keep_id3}")
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise models_module.RepairError("not a RIFF/WAVE file")

    chunks, actions = parse_chunks_for_repair(data)
    chunks = trim_incomplete_pcm_data_chunks(chunks, actions)
    id3_indices = [index for index, chunk in enumerate(chunks) if is_id3_chunk(chunk)]
    keep_index: int | None = None
    if keep_id3 == "first" and id3_indices:
        keep_index = id3_indices[0]
    elif keep_id3 == "last" and id3_indices:
        keep_index = id3_indices[-1]

    rebuilt = bytearray(b"RIFF\x00\x00\x00\x00WAVE")
    id3_removed = 0
    for index, chunk in enumerate(chunks):
        if is_id3_chunk(chunk):
            if keep_index is None or index != keep_index or not chunk.payload.startswith(b"ID3"):
                id3_removed += 1
                actions.append(
                    f"removed ID3 chunk at offset {chunk.source_start} size {len(chunk.payload)}"
                )
                continue

        rebuilt.extend(chunk.chunk_id)
        rebuilt.extend(len(chunk.payload).to_bytes(4, "little"))
        rebuilt.extend(chunk.payload)
        if len(chunk.payload) % 2:
            rebuilt.append(0)

    rebuilt[4:8] = (len(rebuilt) - 8).to_bytes(4, "little")
    repaired = bytes(rebuilt)
    changed = repaired != data
    if int.from_bytes(data[4:8], "little") != len(data) - 8:
        actions.append("normalized RIFF root size")
    if id3_removed:
        actions.append(f"removed duplicate/unselected ID3 chunks: {id3_removed}")

    return models_module.ByteRepairResult(
        changed=changed,
        data=repaired,
        actions=result_formatting_module.dedupe(actions),
        id3_seen=len(id3_indices),
        id3_removed=id3_removed,
        original_size=len(data),
        repaired_size=len(repaired),
        mutagen_summary=mutagen_summary(repaired),
    )


def repair_aiff_bytes(data: bytes) -> models_module.ByteRepairResult:
    if len(data) < 12 or data[:4] != b"FORM" or data[8:12] not in {b"AIFF", b"AIFC"}:
        raise models_module.RepairError("not an AIFF/AIFC file")

    chunks, actions = parse_aiff_chunks(data)
    id3_seen = sum(1 for chunk in chunks if chunk.chunk_id == b"ID3 ")
    rebuilt = bytearray(data[:12])
    id3_removed = 0
    for chunk in chunks:
        if chunk.chunk_id == b"ID3 " and not chunk.payload:
            id3_removed += 1
            actions.append(f"removed empty ID3 chunk at offset {chunk.source_start}")
            continue
        rebuilt.extend(chunk.chunk_id)
        rebuilt.extend(len(chunk.payload).to_bytes(4, "big"))
        rebuilt.extend(chunk.payload)
        if len(chunk.payload) % 2:
            rebuilt.append(0)

    rebuilt[4:8] = (len(rebuilt) - 8).to_bytes(4, "big")
    repaired = bytes(rebuilt)
    if int.from_bytes(data[4:8], "big") != len(data) - 8:
        actions.append("normalized FORM root size")
    if id3_removed:
        actions.append(f"removed empty ID3 chunks: {id3_removed}")

    return models_module.ByteRepairResult(
        changed=repaired != data,
        data=repaired,
        actions=result_formatting_module.dedupe(actions),
        id3_seen=id3_seen,
        id3_removed=id3_removed,
        original_size=len(data),
        repaired_size=len(repaired),
        mutagen_summary=mutagen_aiff_summary(repaired),
    )


def parse_aiff_chunks(data: bytes) -> tuple[list[models_module.ParsedChunk], list[str]]:
    if len(data) < 12 or data[:4] != b"FORM" or data[8:12] not in {b"AIFF", b"AIFC"}:
        raise models_module.RepairError("not an AIFF/AIFC file")
    chunks: list[models_module.ParsedChunk] = []
    actions: list[str] = []
    pos = 12
    while pos < len(data):
        if pos + 8 > len(data):
            if all(byte == 0 for byte in data[pos:]):
                actions.append(f"dropped trailing zero padding bytes at offset {pos} size {len(data) - pos}")
            else:
                actions.append(f"dropped trailing bytes at offset {pos} size {len(data) - pos}")
            break
        chunk_id = data[pos : pos + 4]
        if not is_valid_chunk_id(chunk_id):
            raise models_module.RepairError(f"invalid AIFF chunk ID at offset {pos}: {chunk_id!r}")
        size = int.from_bytes(data[pos + 4 : pos + 8], "big")
        data_offset = pos + 8
        unpadded_end = data_offset + size
        padded_end = unpadded_end + (size % 2)
        if padded_end > len(data):
            raise models_module.RepairError(f"truncated AIFF chunk at offset {pos}: {chunk_id!r}")
        chunks.append(
            models_module.ParsedChunk(
                chunk_id=chunk_id,
                payload=data[data_offset:unpadded_end],
                source_start=pos,
                source_end=padded_end,
            )
        )
        pos = padded_end
    if not any(chunk.chunk_id == b"SSND" for chunk in chunks):
        raise models_module.RepairError("no SSND chunk found")
    return chunks, actions


def has_empty_aiff_id3_chunks(data: bytes) -> bool:
    try:
        chunks, _ = parse_aiff_chunks(data)
    except models_module.RepairError:
        return False
    return any(chunk.chunk_id == b"ID3 " and not chunk.payload for chunk in chunks)


def parse_chunks_for_repair(data: bytes) -> tuple[list[models_module.ParsedChunk], list[str]]:
    chunks: list[models_module.ParsedChunk] = []
    actions: list[str] = []
    pos = 12
    found_data = False

    while pos < len(data):
        if pos + 8 > len(data):
            if all(byte == 0 for byte in data[pos:]):
                actions.append(f"dropped trailing zero padding bytes at offset {pos} size {len(data) - pos}")
            else:
                actions.append(f"dropped trailing bytes at offset {pos} size {len(data) - pos}")
            break

        chunk_id = data[pos : pos + 4]
        if not is_valid_chunk_id(chunk_id):
            if found_data:
                marker = find_next_id3_chunk(data, pos)
                if marker is not None:
                    actions.append(f"dropped invalid bytes at offset {pos} size {marker - pos}")
                    pos = marker
                    continue
                actions.append(f"dropped unparseable tail at offset {pos} size {len(data) - pos}")
                break
            raise models_module.RepairError(f"invalid chunk ID before audio data at offset {pos}: {chunk_id!r}")

        size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        data_offset = pos + 8
        unpadded_end = data_offset + size
        padded_end = unpadded_end + (size % 2)

        if chunk_id == b"LIST" and size < 4 and found_data:
            actions.append(f"removed invalid empty LIST chunk at offset {pos}")
            pos = unpadded_end
            continue

        if padded_end > len(data):
            if chunk_id == b"data" and unpadded_end == len(data):
                chunks.append(
                    models_module.ParsedChunk(
                        chunk_id=chunk_id,
                        payload=data[data_offset:unpadded_end],
                        source_start=pos,
                        source_end=unpadded_end,
                    )
                )
                actions.append(f"inserted missing RIFF padding after final data chunk at offset {pos}")
                found_data = True
                pos = unpadded_end
                continue
            if chunk_id == b"data":
                marker = find_next_id3_chunk(data, data_offset)
                if marker is not None and marker > data_offset:
                    payload = data[data_offset:marker]
                    chunks.append(
                        models_module.ParsedChunk(
                            chunk_id=chunk_id,
                            payload=payload,
                            source_start=pos,
                            source_end=marker,
                        )
                    )
                    actions.append(
                        f"shrunk oversized data chunk at offset {pos} "
                        f"from declared size {size} to {len(payload)}"
                    )
                    found_data = True
                    pos = marker
                    continue
            if found_data:
                marker = find_next_id3_chunk(data, data_offset)
                if marker is not None and marker > data_offset:
                    payload = data[data_offset:marker]
                    chunks.append(
                        models_module.ParsedChunk(
                            chunk_id=chunk_id,
                            payload=payload,
                            source_start=pos,
                            source_end=marker,
                        )
                    )
                    actions.append(
                        f"shrunk oversized {chunk_id.decode('ascii', 'replace').strip()} "
                        f"chunk at offset {pos} before ID3 offset {marker}"
                    )
                    if chunk_id == b"data":
                        found_data = True
                    pos = marker
                    continue
            actions.append(f"dropped truncated tail at offset {pos} size {len(data) - pos}")
            break

        source_end = padded_end
        if size % 2 and looks_like_chunk_at(data, unpadded_end):
            source_end = unpadded_end
            actions.append(
                f"inserted missing RIFF padding after odd-sized "
                f"{chunk_id.decode('ascii', 'replace').strip()} chunk at offset {pos}"
            )

        payload = data[data_offset:unpadded_end]
        chunks.append(models_module.ParsedChunk(chunk_id=chunk_id, payload=payload, source_start=pos, source_end=source_end))
        if chunk_id == b"data":
            found_data = True
        pos = source_end

    if not any(chunk.chunk_id == b"data" for chunk in chunks):
        raise models_module.RepairError("no data chunk found")
    return chunks, actions


def data_payload_hash(data: bytes) -> str:
    return hashlib.sha256(data_payload(data)).hexdigest()


def data_payload(data: bytes) -> bytes:
    pos = 12
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        if not is_valid_chunk_id(chunk_id):
            break
        size = int.from_bytes(data[pos + 4 : pos + 8], "little")
        data_offset = pos + 8
        unpadded_end = data_offset + size
        padded_end = unpadded_end + (size % 2)
        if chunk_id == b"data":
            if unpadded_end <= len(data):
                return data[data_offset:unpadded_end]
            marker = find_next_id3_chunk(data, data_offset)
            if marker is not None and marker > data_offset:
                return data[data_offset:marker]
            break
        if size % 2 and looks_like_chunk_at(data, unpadded_end):
            pos = unpadded_end
        else:
            pos = padded_end
    raise models_module.RepairError("no readable data chunk found")


def trim_incomplete_pcm_data_chunks(chunks: list[models_module.ParsedChunk], actions: list[str]) -> list[models_module.ParsedChunk]:
    block_align = pcm_wave_block_align(chunks)
    if block_align is None:
        return chunks

    repaired_chunks: list[models_module.ParsedChunk] = []
    for chunk in chunks:
        if chunk.chunk_id != b"data":
            repaired_chunks.append(chunk)
            continue
        remainder = len(chunk.payload) % block_align
        if remainder == 0:
            repaired_chunks.append(chunk)
            continue
        repaired_chunks.append(
            models_module.ParsedChunk(
                chunk_id=chunk.chunk_id,
                payload=chunk.payload[:-remainder],
                source_start=chunk.source_start,
                source_end=chunk.source_end,
            )
        )
        actions.append(
            f"trimmed incomplete PCM data tail at offset {chunk.source_start + 8} "
            f"size {remainder} for block align {block_align}"
        )
    return repaired_chunks


def pcm_wave_block_align(chunks: Iterable[models_module.ParsedChunk]) -> int | None:
    fmt_chunk = next((chunk for chunk in chunks if chunk.chunk_id == b"fmt "), None)
    if fmt_chunk is None or len(fmt_chunk.payload) < 16:
        return None
    audio_format = int.from_bytes(fmt_chunk.payload[0:2], "little")
    block_align = int.from_bytes(fmt_chunk.payload[12:14], "little")
    if audio_format not in config_module.PCM_WAVE_FORMAT_CODES or block_align == 0:
        return None
    return block_align


def aligned_pcm_data_payload_hash(data: bytes) -> str:
    chunks, _ = parse_chunks_for_repair(data)
    data_chunk = next(chunk for chunk in chunks if chunk.chunk_id == b"data")
    block_align = pcm_wave_block_align(chunks)
    payload = data_chunk.payload
    if block_align is not None:
        payload = payload[: len(payload) - (len(payload) % block_align)]
    return hashlib.sha256(payload).hexdigest()


def validate_pcm_data_block_alignment(data: bytes) -> None:
    chunks, _ = parse_chunks_for_repair(data)
    block_align = pcm_wave_block_align(chunks)
    if block_align is None:
        return
    for chunk in chunks:
        if chunk.chunk_id != b"data":
            continue
        remainder = len(chunk.payload) % block_align
        if remainder:
            raise models_module.RepairError(
                f"PCM data chunk at offset {chunk.source_start} has {remainder} trailing byte(s) "
                f"that do not complete block align {block_align}"
            )


def aiff_sound_payload_hash(data: bytes) -> str:
    return hashlib.sha256(aiff_sound_payload(data)).hexdigest()


def aiff_sound_payload(data: bytes) -> bytes:
    chunks, _ = parse_aiff_chunks(data)
    for chunk in chunks:
        if chunk.chunk_id == b"SSND":
            return chunk.payload
    raise models_module.RepairError("no readable SSND chunk found")


def is_id3_chunk(chunk: models_module.ParsedChunk) -> bool:
    return chunk.chunk_id in config_module.ID3_CHUNK_IDS


def is_valid_chunk_id(chunk_id: bytes) -> bool:
    return len(chunk_id) == 4 and all(32 <= byte <= 126 for byte in chunk_id)


def looks_like_chunk_at(data: bytes, pos: int) -> bool:
    if pos + 8 > len(data):
        return False
    chunk_id = data[pos : pos + 4]
    if not is_valid_chunk_id(chunk_id):
        return False
    size = int.from_bytes(data[pos + 4 : pos + 8], "little")
    if chunk_id in config_module.ID3_CHUNK_IDS:
        return data[pos + 8 : pos + 11] == b"ID3"
    if chunk_id == b"LIST" and size < 4:
        return True
    return pos + 8 + size + (size % 2) <= len(data) + 1


def find_next_id3_chunk(data: bytes, start: int) -> int | None:
    best: int | None = None
    for marker in config_module.ID3_CHUNK_IDS:
        pos = data.find(marker, start)
        while pos != -1:
            if pos + 11 <= len(data) and data[pos + 8 : pos + 11] == b"ID3":
                if best is None or pos < best:
                    best = pos
                break
            pos = data.find(marker, pos + 1)
    return best


def mutagen_summary(data: bytes) -> str | None:
    try:
        from mutagen.wave import WAVE
    except Exception:
        return None
    try:
        audio = WAVE(BytesIO(data))
    except Exception as error:
        return f"mutagen error: {error}"
    length = getattr(getattr(audio, "info", None), "length", None)
    if audio.tags is None:
        return f"mutagen ok length={length:.3f} tags=no" if isinstance(length, float) else "mutagen ok tags=no"
    keys = sorted(text_safety_module.mutagen_key_label(key) for key in audio.tags.keys())
    return (
        f"mutagen ok length={length:.3f} tags=yes keys={','.join(keys[:8])}"
        if isinstance(length, float)
        else f"mutagen ok tags=yes keys={','.join(keys[:8])}"
    )


def mutagen_aiff_summary(data: bytes) -> str | None:
    try:
        from mutagen.aiff import AIFF
    except Exception:
        return None
    try:
        audio = AIFF(BytesIO(data))
    except Exception as error:
        return f"mutagen error: {error}"
    length = getattr(getattr(audio, "info", None), "length", None)
    if audio.tags is None:
        return f"mutagen ok length={length:.3f} tags=no" if isinstance(length, float) else "mutagen ok tags=no"
    keys = sorted(text_safety_module.mutagen_key_label(key) for key in audio.tags.keys())
    return (
        f"mutagen ok length={length:.3f} tags=yes keys={','.join(keys[:8])}"
        if isinstance(length, float)
        else f"mutagen ok tags=yes keys={','.join(keys[:8])}"
    )
