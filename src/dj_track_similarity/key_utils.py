from __future__ import annotations

import re


CAMEL0T_PATTERN = re.compile(r"^\s*0?(1[0-2]|[1-9])\s*([ab])\s*$", re.IGNORECASE)
NOTE_ALIASES = {
    "c": "C",
    "b#": "C",
    "c#": "C#",
    "db": "C#",
    "d": "D",
    "d#": "D#",
    "eb": "D#",
    "e": "E",
    "fb": "E",
    "e#": "F",
    "f": "F",
    "f#": "F#",
    "gb": "F#",
    "g": "G",
    "g#": "G#",
    "ab": "G#",
    "a": "A",
    "a#": "A#",
    "bb": "A#",
    "b": "B",
    "cb": "B",
}
CAMEL0T_MINOR = {
    "G#": "1A",
    "D#": "2A",
    "A#": "3A",
    "F": "4A",
    "C": "5A",
    "G": "6A",
    "D": "7A",
    "A": "8A",
    "E": "9A",
    "B": "10A",
    "F#": "11A",
    "C#": "12A",
}
CAMEL0T_MAJOR = {
    "B": "1B",
    "F#": "2B",
    "C#": "3B",
    "G#": "4B",
    "D#": "5B",
    "A#": "6B",
    "F": "7B",
    "C": "8B",
    "G": "9B",
    "D": "10B",
    "A": "11B",
    "E": "12B",
}


def camelot_key_from_sonara_analysis(analysis: dict[str, object]) -> str | None:
    for key in ("camelot_key", "camelot", "open_key"):
        value = _optional_string(analysis.get(key))
        if value:
            parsed = parse_existing_camelot(value)
            if parsed:
                return parsed

    for key in ("key", "key_detection", "detect_key", "predominant_key"):
        value = _optional_string(analysis.get(key))
        camelot = key_name_to_camelot(value)
        if camelot:
            return camelot

    chord = _optional_string(analysis.get("predominant_chord"))
    if chord:
        camelot = key_name_to_camelot(chord)
        if camelot:
            return camelot
    return None


def camelot_source_feature(analysis: dict[str, object]) -> str:
    for key in ("camelot_key", "camelot", "open_key", "key", "key_detection", "detect_key", "predominant_key", "predominant_chord"):
        value = _optional_string(analysis.get(key))
        if value and (parse_existing_camelot(value) or key_name_to_camelot(value)):
            return key
    return "none"


def parse_existing_camelot(value: str) -> str | None:
    match = CAMEL0T_PATTERN.match(value)
    if not match:
        return None
    return f"{int(match.group(1))}{match.group(2).upper()}"


def key_name_to_camelot(value: str | None) -> str | None:
    if not value:
        return None
    existing = parse_existing_camelot(value)
    if existing:
        return existing

    cleaned = (
        value.strip()
        .replace("♭", "b")
        .replace("♯", "#")
        .replace(" minor", " min")
        .replace(" major", " maj")
    )
    tokens = re.findall(r"[A-Ga-g](?:#|b| sharp| flat)?|maj|min|major|minor|m\b", cleaned)
    if not tokens:
        return None
    note = _normalize_note_token(tokens[0])
    if not note:
        return None
    lowered = cleaned.lower()
    mode = "minor" if re.search(r"(^|[^a-z])(min|minor|m)([^a-z]|$)", lowered) else "major"
    if re.search(r"(^|[^a-z])(maj|major)([^a-z]|$)", lowered):
        mode = "major"
    if re.match(r"^[A-Ga-g](?:#|b)?m(?:\d|$)", cleaned):
        mode = "minor"
    return (CAMEL0T_MINOR if mode == "minor" else CAMEL0T_MAJOR).get(note)


def _normalize_note_token(token: str) -> str | None:
    cleaned = token.lower().replace(" sharp", "#").replace(" flat", "b").replace(" ", "")
    return NOTE_ALIASES.get(cleaned)


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
