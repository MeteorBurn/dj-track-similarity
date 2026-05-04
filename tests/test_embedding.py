import numpy as np

from dj_track_similarity.embedding import _call_clap_audio_processor


class StrictClapProcessor:
    def __call__(self, *, audio, sampling_rate, return_tensors, padding):
        return {
            "audio": audio,
            "sampling_rate": sampling_rate,
            "return_tensors": return_tensors,
            "padding": padding,
        }


def test_clap_audio_processor_uses_singular_audio_keyword() -> None:
    batch = [np.zeros(8, dtype=np.float32)]

    result = _call_clap_audio_processor(StrictClapProcessor(), batch, 48_000)

    assert result == {
        "audio": batch,
        "sampling_rate": 48_000,
        "return_tensors": "pt",
        "padding": True,
    }
