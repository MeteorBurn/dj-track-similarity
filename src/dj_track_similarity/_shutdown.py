from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager


@contextmanager
def defer_keyboard_interrupt() -> Iterator[Callable[[Callable[[], object]], None]]:
    """Finish retry-safe shutdown operations before propagating Ctrl+C."""
    original_error = sys.exc_info()[1]
    interrupted: KeyboardInterrupt | None = None

    def finish(operation: Callable[[], object]) -> None:
        nonlocal interrupted
        while True:
            try:
                operation()
                return
            except KeyboardInterrupt as error:
                if interrupted is None:
                    interrupted = error

    yield finish
    # Cleanup may run inside a finally whose original error must survive a
    # second interrupt, even though that error did not enter this context.
    if interrupted is not None and original_error is None:
        raise interrupted
