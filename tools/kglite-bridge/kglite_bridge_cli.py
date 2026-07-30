"""CLI entry point for the read-only SQLite to KGLite bridge."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from kglite_bridge import (
    BridgeError,
    BuildOptions,
    build_projection,
    write_kglite_graph,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build a disposable KGLite metadata/similarity graph from a "
            "query-only Core + Artifacts snapshot."
        )
    )
    parser.add_argument("--db", required=True, type=Path, help="Core SQLite path")
    parser.add_argument(
        "--artifacts",
        type=Path,
        help="Artifacts sidecar path (default: <db stem>.artifacts.sqlite)",
    )
    parser.add_argument("--output", required=True, type=Path, help="Output .kgl path")
    parser.add_argument(
        "--source",
        action="append",
        choices=("active", "maest", "mert", "muq", "clap", "sonara"),
        help=(
            "Embedding source; repeat for an explicit set. Default/active "
            "auto-selects every embedding source with stored rows."
        ),
    )
    parser.add_argument(
        "--top-k", type=int, default=10, help="Neighbours per seed/source"
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.0,
        help="Minimum cosine similarity in [-1, 1]",
    )
    parser.add_argument(
        "--omit-paths",
        action="store_true",
        help="Do not include stored audio file paths in Track nodes",
    )
    parser.add_argument(
        "--integrity-check",
        action="store_true",
        help="Run SQLite quick_check on both read-only snapshots",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Atomically replace an existing disposable .kgl output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and calculate the projection without writing .kgl",
    )
    parser.add_argument(
        "--batch-size", type=int, default=500, help="KGLite write batch"
    )
    parser.add_argument(
        "--similarity-block-size",
        type=int,
        default=512,
        help="Rows per NumPy cosine block",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Status output format",
    )
    return parser


def _sources(values: list[str] | None) -> tuple[str, ...] | None:
    if not values or values == ["active"]:
        return None
    if "active" in values:
        raise BridgeError("'active' cannot be combined with explicit --source values")
    return tuple(values)


def _text_report(payload: dict[str, object], output: Path | None) -> str:
    lines = [
        f"projection: {payload['projection_digest']}",
        f"catalog: {payload['catalog_uuid']}",
        f"sources: {', '.join(payload['selected_sources']) or '(none)'}",
        f"nodes: {payload['node_count']}",
        f"edges: {payload['edge_count']}",
    ]
    if output is not None:
        lines.append(f"output: {output}")
    for source in payload["source_reports"]:
        assert isinstance(source, dict)
        lines.append(
            "{family}: vectors={valid_vectors}, edges={similarity_edges}, "
            "inactive={inactive_rows}, stale={stale_rows}".format(**source)
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        options = BuildOptions(
            core_path=args.db,
            artifacts_path=args.artifacts,
            sources=_sources(args.source),
            top_k=args.top_k,
            min_score=args.min_score,
            include_paths=not args.omit_paths,
            integrity_check=args.integrity_check,
            similarity_block_size=args.similarity_block_size,
        ).normalized()
        projection = build_projection(options)
        output = None
        if not args.dry_run:
            assert options.artifacts_path is not None
            output = write_kglite_graph(
                projection,
                args.output,
                core_path=options.core_path,
                artifacts_path=options.artifacts_path,
                overwrite=args.overwrite,
                batch_size=args.batch_size,
            )
        payload = projection.report.to_dict()
        payload["dry_run"] = bool(args.dry_run)
        payload["output"] = None if output is None else str(output)
        if args.format == "json":
            print(json.dumps(payload, sort_keys=True, ensure_ascii=False))
        else:
            print(_text_report(payload, output))
        return 0
    except BridgeError as error:
        print(f"kglite-bridge: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
