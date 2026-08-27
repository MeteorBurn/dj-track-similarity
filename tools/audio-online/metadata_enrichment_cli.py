from __future__ import annotations

import argparse
from collections.abc import Sequence
import os
from pathlib import Path
import shutil
import webbrowser

from metadata_enrichment.config import load_config
from metadata_enrichment.auth import authorize_lastfm
from metadata_enrichment.beatport_auth import authorize_beatport, check_beatport_auth, ensure_beatport_access_token
from metadata_enrichment.http import get_json, post_form_json
from metadata_enrichment.inputs import load_tracks
from metadata_enrichment.local_library import read_local_evidence
from metadata_enrichment.models import LocalEvidence
from metadata_enrichment.report import build_report_contract, write_workbook
from metadata_enrichment.sources import collect_source_results, source_registry


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect independent online track metadata.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    enrich = subcommands.add_parser("enrich", help="Create a metadata workbook.")
    enrich.add_argument("--input", required=True, type=Path)
    enrich.add_argument("--output", required=True, type=Path)
    enrich.add_argument("--config", type=Path, default=Path(__file__).with_name("config.toml"))
    enrich.add_argument("--db", type=Path)
    node = os.environ.get("METADATA_ENRICHMENT_NODE") or shutil.which("node")
    enrich.add_argument("--node-executable", type=Path, default=Path(node) if node else None)
    node_modules = os.environ.get("METADATA_ENRICHMENT_NODE_MODULES")
    enrich.add_argument("--node-modules", type=Path, default=Path(node_modules) if node_modules else None)
    authorize = subcommands.add_parser("authorize", help="Authorize one configured source.")
    authorize.add_argument("source")
    authorize.add_argument("--config", type=Path, default=Path(__file__).with_name("config.toml"))
    check_auth = subcommands.add_parser("check-auth", help="Validate a saved source authorization.")
    check_auth.add_argument("source")
    check_auth.add_argument("--config", type=Path, default=Path(__file__).with_name("config.toml"))
    args = parser.parse_args(argv)
    if args.command == "enrich":
        if args.node_executable is None or args.node_modules is None:
            parser.error("XLSX export requires node plus METADATA_ENRICHMENT_NODE_MODULES (or --node-executable and --node-modules)")
        tracks = load_tracks(args.input, node_executable=args.node_executable, node_modules=args.node_modules)
        config = load_config(args.config)
        beatport = config.sources.get("beatport", {})
        if isinstance(beatport, dict) and isinstance(beatport.get("client_id"), str) and isinstance(beatport.get("client_secret"), str) and beatport["client_id"] and beatport["client_secret"]:
            config = ensure_beatport_access_token(args.config, config, post_form_json=post_form_json)
        sources = source_registry(config)
        reports = []
        for track in tracks:
            local = read_local_evidence(args.db, track) if args.db else LocalEvidence()
            reports.append((track, local, collect_source_results(track, sources)))
        write_workbook(build_report_contract(reports, tuple(source.name for source in sources)), args.output, node_executable=args.node_executable, node_modules=args.node_modules)
        print(f"Wrote {args.output} ({len(tracks)} tracks)")
    elif args.command == "authorize":
        config = load_config(args.config)
        if args.source == "lastfm":
            print(authorize_lastfm(str(args.config), config, opener=webbrowser.open, input_fn=input, get_json=get_json))
        elif args.source == "beatport":
            print(authorize_beatport(args.config, config, post_form_json=post_form_json))
        else:
            parser.error(f"{args.source} has no supported configured OAuth flow")
    elif args.command == "check-auth":
        config = load_config(args.config)
        if args.source != "beatport":
            parser.error(f"{args.source} has no supported authorization check")
        response = check_beatport_auth(config, get_json=get_json)
        if response.get("active") is True:
            scope = response.get("scope")
            suffix = f" scope={scope}" if isinstance(scope, str) and scope else ""
            print(f"Beatport authorization is valid.{suffix}")
        else:
            print("Beatport authorization is invalid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
