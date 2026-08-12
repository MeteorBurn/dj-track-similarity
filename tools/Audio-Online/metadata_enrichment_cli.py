from __future__ import annotations

import argparse
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect independent online track metadata.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("enrich", help="Create a metadata workbook.")
    authorize = subcommands.add_parser("authorize", help="Authorize one configured source.")
    authorize.add_argument("source")
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
