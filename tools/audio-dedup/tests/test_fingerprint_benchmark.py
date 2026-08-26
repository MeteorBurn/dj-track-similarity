from __future__ import annotations

from pathlib import Path
import sys


TOOL_ROOT = Path(__file__).resolve().parents[1]
if str(TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOL_ROOT))

from benchmark_fingerprint_candidates import run_benchmark  # noqa: E402


def test_benchmark_reports_order_independent_union_and_retrieval_recall() -> None:
    result = run_benchmark(group_count=8, distractor_count=16, seed=17)

    fingerprint = result["strategies"]["fingerprint_lsh"]
    embedding = result["strategies"]["embedding_lsh"]
    union = result["strategies"]["union"]

    assert fingerprint["duplicate_retrieval_recall"] > 0.0
    assert (
        union["duplicate_retrieval_recall"] >= fingerprint["duplicate_retrieval_recall"]
    )
    assert (
        union["duplicate_retrieval_recall"] >= embedding["duplicate_retrieval_recall"]
    )
    assert (
        result["ordering"]["fingerprint_then_embedding_pair_count"]
        == result["ordering"]["embedding_then_fingerprint_pair_count"]
    )
    assert result["ordering"]["candidate_sets_equal"] is True
