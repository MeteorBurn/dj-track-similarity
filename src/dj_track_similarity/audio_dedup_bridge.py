"""Single import boundary between the server and the Audio Dedup tool.

The tool lives under ``tools/audio-dedup`` and is not a packaged module, so the
server cannot import it directly. Its modules import their siblings
relatively, which means loading a module by file path fails outright: the
package directory has to be on ``sys.path`` and the package imported by name.
Keeping that one insertion here leaves the rest of the server free of tool-tree
knowledge.

The import is in-process on purpose. ``run_report`` accepts the already-open
``LibraryDatabase`` plus progress and cancel hooks, and none of those survive a
subprocess boundary, so a scan launched any other way could be neither observed
nor stopped.
"""

from __future__ import annotations

from pathlib import Path
from importlib import import_module
import sys
from types import ModuleType

TOOL_ROOT = Path(__file__).resolve().parents[2] / "tools" / "audio-dedup"


def load_audio_dedup_module(name: str) -> ModuleType:
    """Import a named Audio Dedup module, or explain why it is unavailable."""
    if not TOOL_ROOT.is_dir():
        raise RuntimeError(f"Audio Dedup tool is unavailable: {TOOL_ROOT}")
    tool_root_text = str(TOOL_ROOT)
    if tool_root_text not in sys.path:
        sys.path.insert(0, tool_root_text)
    try:
        module = import_module(f"audio_dedup.{name}")
    except ImportError as error:
        raise RuntimeError(f"Audio Dedup tool is unavailable: {error}") from error
    return module
