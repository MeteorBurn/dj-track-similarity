from __future__ import annotations

from collections.abc import Mapping, Sequence
import csv
from pathlib import Path
from typing import Protocol, TypeAlias

CsvValue: TypeAlias = str | int | float | bool | None
CsvRow: TypeAlias = Mapping[str, CsvValue]


class CsvExportRow(Protocol):
    def csv_row(self) -> CsvRow:
        ...


def write_csv_rows(path: str | Path, fieldnames: Sequence[str], rows: Sequence[CsvExportRow]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.csv_row())
