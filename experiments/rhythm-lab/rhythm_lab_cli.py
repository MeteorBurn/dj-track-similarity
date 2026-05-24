from __future__ import annotations

from pathlib import Path
import sys


LAB_ROOT = Path(__file__).resolve().parent
REPO_ROOT = LAB_ROOT.parents[1]
sys.path.insert(0, str(LAB_ROOT))
sys.path.insert(0, str(REPO_ROOT / "src"))

from rhythm_lab.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
