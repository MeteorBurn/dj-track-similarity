from dj_track_similarity import scanner


def test_scanner_supports_extended_audio_formats() -> None:
    expected = {
        ".aac": "AAC",
        ".ape": "APE",
        ".wma": "WMA",
        ".wv": "WavPack",
    }

    assert expected.keys() <= scanner.SUPPORTED_AUDIO_EXTENSIONS
    assert {
        extension: scanner.DISPLAY_AUDIO_FORMATS[extension]
        for extension in expected
    } == expected
