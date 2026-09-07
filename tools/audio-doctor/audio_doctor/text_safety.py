from __future__ import annotations

MUTAGEN_KEY_TEXT_LIMIT = 160


def xml_safe_text(text: str, *, limit: int | None = None) -> str:
    safe = "".join(char if is_xml_character(char) else escaped_codepoint(char) for char in text)
    if limit is None or len(safe) <= limit:
        return safe
    suffix = f" ... [truncated; original {len(safe)} chars]"
    if len(suffix) >= limit:
        return suffix[:limit]
    return safe[: limit - len(suffix)] + suffix


def is_xml_character(char: str) -> bool:
    codepoint = ord(char)
    if codepoint in {0x9, 0xA, 0xD}:
        return True
    if codepoint < 0x20 or 0x7F <= codepoint <= 0x9F:
        return False
    return (
        0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )


def escaped_codepoint(char: str) -> str:
    codepoint = ord(char)
    if codepoint <= 0xFF:
        return f"\\x{codepoint:02x}"
    if codepoint <= 0xFFFF:
        return f"\\u{codepoint:04x}"
    return f"\\U{codepoint:08x}"


def mutagen_key_label(key: object) -> str:
    return xml_safe_text(str(key), limit=MUTAGEN_KEY_TEXT_LIMIT)
