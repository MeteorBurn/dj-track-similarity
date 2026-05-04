import numpy as np

from dj_track_similarity.embedding import _call_clap_audio_processor, _model_output_to_numpy


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


def test_model_output_to_numpy_accepts_pooler_output_object() -> None:
    class TensorLike:
        def detach(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return np.array([[0.0, 1.0, 0.0]], dtype=np.float32)

    class Output:
        pooler_output = TensorLike()

    result = _model_output_to_numpy(Output())

    assert result.tolist() == [[0.0, 1.0, 0.0]]
