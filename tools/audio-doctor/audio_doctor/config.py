from __future__ import annotations

from pathlib import Path




READBACK_FAILURE = "Genre tag was not readable after WAV save:"
ID3_CHUNK_IDS = {b"id3 ", b"ID3 "}
PCM_WAVE_FORMAT_CODES = {1, 3}
PACKAGE_DIR = Path(__file__).resolve().parent
TOOL_ROOT = PACKAGE_DIR.parent
DEFAULT_OUT_DIR = TOOL_ROOT / "data" / "reports"
DEFAULT_RUN_DIR = TOOL_ROOT / "data" / "state"
DEFAULT_BACKUP_DIR = TOOL_ROOT / "data" / "backups"
AUDIO_EXTENSIONS = {
    ".aif",
    ".aiff",
    ".alac",
    ".aac",
    ".aifc",
    ".ape",
    ".dff",
    ".dsf",
    ".flac",
    ".mka",
    ".m4a",
    ".oga",
    ".ogg",
    ".opus",
    ".mp3",
    ".mp4",
    ".tta",
    ".wav",
    ".wave",
    ".wma",
    ".wv",
}
EXPECTED_FORMAT_BY_EXTENSION = {
    ".aif": {"aiff"},
    ".aiff": {"aiff"},
    ".aifc": {"aiff"},
    ".aac": {"aac"},
    ".alac": {"mov,mp4,m4a,3gp,3g2,mj2", "mp4"},
    ".ape": {"ape"},
    ".dff": {"dsf"},
    ".dsf": {"dsf"},
    ".flac": {"flac"},
    ".mka": {"matroska,webm", "matroska"},
    ".m4a": {"mov,mp4,m4a,3gp,3g2,mj2", "mp4"},
    ".mp3": {"mp3"},
    ".mp4": {"mov,mp4,m4a,3gp,3g2,mj2", "mp4"},
    ".oga": {"ogg"},
    ".ogg": {"ogg"},
    ".opus": {"ogg"},
    ".tta": {"tta"},
    ".wav": {"wav"},
    ".wave": {"wav"},
    ".wma": {"asf"},
    ".wv": {"wv"},
}
EXPECTED_CODECS_BY_EXTENSION = {
    ".aac": {"aac"},
    ".aif": {"pcm_s8", "pcm_s16be", "pcm_s24be", "pcm_s32be", "pcm_f32be", "pcm_f64be"},
    ".aiff": {"pcm_s8", "pcm_s16be", "pcm_s24be", "pcm_s32be", "pcm_f32be", "pcm_f64be"},
    ".aifc": {"pcm_s8", "pcm_s16be", "pcm_s24be", "pcm_s32be", "pcm_f32be", "pcm_f64be"},
    ".ape": {"ape"},
    ".dff": {"dsd_lsbf", "dsd_msbf"},
    ".dsf": {"dsd_lsbf", "dsd_msbf"},
    ".flac": {"flac"},
    ".m4a": {"aac", "alac"},
    ".mp3": {"mp3"},
    ".mp4": {"aac", "alac", "mp3"},
    ".oga": {"vorbis", "opus", "flac"},
    ".ogg": {"vorbis", "opus"},
    ".opus": {"opus"},
    ".tta": {"tta"},
    ".wav": {
        "adpcm_ima_wav",
        "adpcm_ms",
        "pcm_alaw",
        "pcm_f32le",
        "pcm_f64le",
        "pcm_mulaw",
        "pcm_s16le",
        "pcm_s24le",
        "pcm_s32le",
        "pcm_s8",
        "pcm_u8",
    },
    ".wave": {
        "adpcm_ima_wav",
        "adpcm_ms",
        "pcm_alaw",
        "pcm_f32le",
        "pcm_f64le",
        "pcm_mulaw",
        "pcm_s16le",
        "pcm_s24le",
        "pcm_s32le",
        "pcm_s8",
        "pcm_u8",
    },
    ".wma": {"wmav1", "wmav2", "wmapro", "wmall", "wmalossless"},
    ".wv": {"wavpack"},
}
FULL_DECODE_TIMEOUT_SECONDS = 600
