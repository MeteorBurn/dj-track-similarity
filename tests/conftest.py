from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from dj_track_similarity.logging_config import LOG_ENV_VAR


@pytest.fixture(autouse=True, scope="session")
def temporary_file_logging(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Keep suite file logging out of the project ``logs`` directory.

    ``configure_logging`` falls back to ``logs/dj-track-similarity.log`` relative
    to the current working directory, so tests that build the API app or open a
    CLI database would otherwise append to the user's real project log.
    """

    log_path = tmp_path_factory.mktemp("app-logs") / "dj-track-similarity.log"
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(LOG_ENV_VAR, str(log_path))
        yield log_path
