from __future__ import annotations

from html import escape
import zipfile
from pathlib import Path

from . import text_safety as text_safety_module

EXCEL_CELL_TEXT_LIMIT = 32767


def write_xlsx_report(path: Path, payload: dict[str, object]) -> None:
    sheets = [
        ("Summary", _summary_sheet_rows(payload)),
        ("Results", _results_sheet_rows(payload)),
        ("Problems", _problems_sheet_rows(payload)),
    ]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _xlsx_writestr(archive, "[Content_Types].xml", _xlsx_content_types(len(sheets)))
        _xlsx_writestr(archive, "_rels/.rels", _xlsx_root_rels())
        _xlsx_writestr(archive, "docProps/app.xml", _xlsx_app_props())
        _xlsx_writestr(archive, "docProps/core.xml", _xlsx_core_props(str(payload["generated_at"])))
        _xlsx_writestr(archive, "xl/workbook.xml", _xlsx_workbook_xml([name for name, _ in sheets]))
        _xlsx_writestr(archive, "xl/_rels/workbook.xml.rels", _xlsx_workbook_rels(len(sheets)))
        _xlsx_writestr(archive, "xl/styles.xml", _xlsx_styles_xml())
        for index, (name, rows) in enumerate(sheets, start=1):
            _xlsx_writestr(archive, f"xl/worksheets/sheet{index}.xml", _xlsx_sheet_xml(name, rows))


def _xlsx_writestr(archive: zipfile.ZipFile, filename: str, content: str) -> None:
    info = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, content)


def _summary_sheet_rows(payload: dict[str, object]) -> list[list[object]]:
    state = payload.get("state", {})
    options = payload.get("options", {})
    source_counts = payload.get("source_counts", {})
    status_counts = payload.get("status_counts", {})
    reason_counts = payload.get("reason_counts", {})
    assert isinstance(state, dict)
    assert isinstance(options, dict)
    assert isinstance(source_counts, dict)
    assert isinstance(status_counts, dict)
    assert isinstance(reason_counts, dict)
    rows: list[list[object]] = [
        ["Audio Doctor summary"],
        ["Generated at", payload["generated_at"]],
        ["Mode", payload["mode"]],
        ["Total collected", payload["total_collected"]],
        ["Processed results", payload.get("processed_count", payload["result_count"])],
        ["State results in report", payload.get("state_result_count", 0)],
        ["Report results", payload["result_count"]],
        ["Missing DB files", payload["missing_db_files"]],
        ["State enabled", state.get("enabled", False)],
        ["State file", state.get("path") or ""],
        ["Skipped from state", state.get("skipped_from_state", 0)],
        ["Skipped by reason", state.get("skipped_by_reason", 0)],
        ["Skipped included in report", state.get("included_in_report", 0)],
        ["Keep ID3 policy", options.get("keep_id3", "")],
        ["Workers", options.get("workers", "")],
        ["Backup directory", options.get("backup_dir", "")],
        ["No backup", options.get("no_backup", False)],
        [],
        ["Input source", "Count"],
    ]
    for label, key in (("Paths", "paths"), ("Folders", "folders"), ("Databases", "databases"), ("Logs", "logs")):
        rows.append([label, source_counts.get(key, 0)])
    rows.extend([[], ["Status", "Count"]])
    for status, count in status_counts.items():
        rows.append([status, count])
    rows.extend([[], ["Reason", "Count"]])
    for reason, count in reason_counts.items():
        rows.append([reason, count])
    return rows


def _results_sheet_rows(payload: dict[str, object]) -> list[list[object]]:
    rows: list[list[object]] = [
        [
            "action",
            "source",
            "status",
            "reason",
            "path",
            "mode",
            "message",
            "detail",
            "original_size",
            "repaired_size",
            "size_delta",
            "id3_seen",
            "id3_removed",
            "primary_action",
            "backup_path",
            "checked_at",
            "modified_at",
            "mutagen_summary",
        ]
    ]
    for result in payload["results"]:  # type: ignore[index]
        assert isinstance(result, dict)
        rows.append(
            [
                result.get("action", ""),
                result.get("source", ""),
                result.get("status_label", ""),
                result.get("reason", ""),
                result.get("path", ""),
                result.get("mode", ""),
                result.get("message", ""),
                result.get("detail", ""),
                result.get("original_size", 0),
                result.get("repaired_size", 0),
                result.get("size_delta", 0),
                result.get("id3_seen", 0),
                result.get("id3_removed", 0),
                result.get("primary_action", ""),
                result.get("backup_path", ""),
                result.get("checked_at", ""),
                result.get("modified_at", ""),
                result.get("mutagen_summary", ""),
            ]
        )
    return rows


def _problems_sheet_rows(payload: dict[str, object]) -> list[list[object]]:
    rows: list[list[object]] = [["problem", "count"]]
    for problem in payload.get("problem_summary", []):
        if not isinstance(problem, dict):
            continue
        rows.append([problem.get("problem", ""), problem.get("count", 0)])
    return rows


def _xlsx_content_types(sheet_count: int) -> str:
    sheet_overrides = "\n".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
{sheet_overrides}
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>'''


def _xlsx_root_rels() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>'''


def _xlsx_app_props() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>dj-track-similarity</Application>
</Properties>'''


def _xlsx_core_props(generated_at: str) -> str:
    timestamp = generated_at if generated_at.endswith("Z") else f"{generated_at}Z"
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>Audio Doctor report</dc:title>
<dc:creator>dj-track-similarity</dc:creator>
<dcterms:created xsi:type="dcterms:W3CDTF">{escape(timestamp)}</dcterms:created>
</cp:coreProperties>'''


def _xlsx_workbook_xml(sheet_names: list[str]) -> str:
    sheets = "\n".join(
        f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheet_names, start=1)
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>
{sheets}
</sheets>
</workbook>'''


def _xlsx_workbook_rels(sheet_count: int) -> str:
    rels = [
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    ]
    rels.append(
        f'<Relationship Id="rId{sheet_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    )
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{"".join(rels)}
</Relationships>'''


def _xlsx_styles_xml() -> str:
    return '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="5">
<font><sz val="11"/><color rgb="FF111827"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><b/><sz val="16"/><color rgb="FF111827"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FF1B5E20"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFB71C1C"/><name val="Calibri"/></font>
</fonts>
<fills count="6">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF263238"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE8F5E9"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFEBEE"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE3F2FD"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFD1D5DB"/></left><right style="thin"><color rgb="FFD1D5DB"/></right><top style="thin"><color rgb="FFD1D5DB"/></top><bottom style="thin"><color rgb="FFD1D5DB"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="6">
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="3" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="4" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''


def _xlsx_sheet_xml(name: str, rows: list[list[object]]) -> str:
    max_cols = max((len(row) for row in rows), default=1)
    col_widths = _xlsx_column_widths(rows, max_cols)
    cols_xml = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(col_widths, start=1)
    )
    sheet_views = ""
    if len(rows) > 1:
        sheet_views = '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
    rows_xml = "\n".join(_xlsx_row_xml(row, row_index, name) for row_index, row in enumerate(rows, start=1))
    dimension = f"A1:{_xlsx_col_name(max_cols)}{max(1, len(rows))}"
    auto_filter = f'<autoFilter ref="A1:{_xlsx_col_name(max_cols)}1"/>' if len(rows) > 1 else ""
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="{dimension}"/>
{sheet_views}
<cols>{cols_xml}</cols>
<sheetData>
{rows_xml}
</sheetData>
{auto_filter}
</worksheet>'''


def _xlsx_row_xml(row: list[object], row_index: int, sheet_name: str) -> str:
    height = ' ht="26" customHeight="1"' if row_index == 1 else ""
    cells = "".join(_xlsx_cell_xml(value, row_index, col_index, _xlsx_style_id(value, row_index, sheet_name)) for col_index, value in enumerate(row, start=1))
    return f'<row r="{row_index}"{height}>{cells}</row>'


def _xlsx_cell_xml(value: object, row_index: int, col_index: int, style_id: int) -> str:
    ref = f"{_xlsx_col_name(col_index)}{row_index}"
    style = f' s="{style_id}"'
    if value is None:
        return f'<c r="{ref}"{style}/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"{style}><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"{style}><v>{value}</v></c>'
    text = escape(text_safety_module.xml_safe_text(str(value), limit=EXCEL_CELL_TEXT_LIMIT))
    return f'<c r="{ref}" t="inlineStr"{style}><is><t>{text}</t></is></c>'


def _xlsx_style_id(value: object, row_index: int, sheet_name: str) -> int:
    if row_index == 1 and sheet_name == "Summary":
        return 2
    if row_index == 1:
        return 1
    if value in {"NO ACTION", "REPAIRED"}:
        return 3
    if value in {"REVIEW MANUALLY", "FAILED"}:
        return 4
    return 5


def _xlsx_column_widths(rows: list[list[object]], max_cols: int) -> list[int]:
    widths: list[int] = []
    for col_index in range(max_cols):
        max_len = 10
        for row in rows:
            if col_index >= len(row):
                continue
            value = row[col_index]
            text = "" if value is None else str(value)
            max_len = max(max_len, min(80, len(text)))
        widths.append(max(12, min(72, max_len + 3)))
    return widths


def _xlsx_col_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name
