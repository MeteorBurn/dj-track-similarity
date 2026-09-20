from __future__ import annotations

from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TOOL_ROOT = SCRIPT_DIR.parent
REPO_ROOT = TOOL_ROOT.parents[1]
DEFAULT_DB = REPO_ROOT / "database" / "volumes.sqlite"
DEFAULT_RHYTHM_LAB_DB = REPO_ROOT / "tools" / "rhythm-lab" / "database" / "rhythm_lab.sqlite"
DEFAULT_OUT_DIR = TOOL_ROOT / "data" / "reports"
FINGERPRINT_REVIEW_MIN_SIMILARITY = 0.45
SONARA_DUPLICATE_MIN_SIMILARITY = 0.30
# Upstream SONARA's own reading of a fingerprint score: its tests put a
# gain-changed copy of the same file above 0.95 ("essentially identical"),
# its README puts genuine duplicates above 0.7, and 0.30 is the threshold it
# calls a safe decision for "same recording".
FINGERPRINT_CONFIDENCE_HIGH = 0.95
FINGERPRINT_CONFIDENCE_MEDIUM = 0.70
MODE_FINGERPRINT_SCAN = "fingerprint_scan"
MODE_FINGERPRINT_LSH = "fingerprint_lsh"
SEARCH_MODES = (MODE_FINGERPRINT_SCAN, MODE_FINGERPRINT_LSH)
DELETION_MODE_PERMANENT = "permanent"
DELETION_MODE_TRASH = "trash"
DELETION_MODES = (DELETION_MODE_PERMANENT, DELETION_MODE_TRASH)
SCORE_SEMANTICS = {
    "fingerprint_similarity": {
        "kind": "sonara_native_fingerprint_match",
        "range": "0..1",
        "notes": "Exact native SONARA fingerprint comparison, the only duplicate evidence this tool reads. fingerprint_scan follows the upstream SONARA recipe and treats a score above 0.30 as the same recording; fingerprint_lsh runs the same comparison after version-separated LSH retrieval and needs 0.45. Group confidence reads this score: high from 0.95, medium from 0.70, manual review below. Every deletion is the reviewer's explicit choice.",
    },
}


def score_semantics_payload() -> dict[str, dict[str, object]]:
    return {key: dict(value) for key, value in SCORE_SEMANTICS.items()}
