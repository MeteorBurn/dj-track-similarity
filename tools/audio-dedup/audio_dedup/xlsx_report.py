from __future__ import annotations

import math
from pathlib import Path
import re
from xml.sax.saxutils import escape
import zipfile

from . import config as config_module


def write_xlsx_report(path: Path, payload: dict[str, object]) -> None:
    sheets = [
        ("Summary", _summary_sheet_rows(payload)),
        ("Groups", _groups_sheet_rows(payload)),
        ("Candidates", _candidates_sheet_rows(payload)),
        ("Pair Evidence", _pair_evidence_sheet_rows(payload)),
        ("Rhythm Lab", _rhythm_lab_sheet_rows(payload)),
    ]
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _xlsx_content_types(len(sheets)))
        archive.writestr("_rels/.rels", _xlsx_root_rels())
        archive.writestr("docProps/app.xml", _xlsx_app_props())
        archive.writestr("docProps/core.xml", _xlsx_core_props(str(payload["generated_at"])))
        archive.writestr("xl/workbook.xml", _xlsx_workbook_xml([name for name, _ in sheets]))
        archive.writestr("xl/_rels/workbook.xml.rels", _xlsx_workbook_rels(len(sheets)))
        archive.writestr("xl/styles.xml", _xlsx_styles_xml())
        for index, (name, rows) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _xlsx_sheet_xml(name, rows))


def _summary_sheet_rows(payload: dict[str, object]) -> list[list[object]]:
    stats = payload.get("statistics", {})
    assert isinstance(stats, dict)
    confidence = stats.get("confidence_counts", {})
    embeddings = stats.get("embedding_coverage", {})
    rhythm_lab = payload.get("rhythm_lab", {})
    path_contains = payload.get("path_contains") or []
    path_filter = ", ".join(str(item) for item in path_contains) if isinstance(path_contains, list) else str(path_contains)
    sources = payload.get("sources", list(config_module.SUPPORTED_EMBEDDINGS))
    source_text = (
        ", ".join(str(item) for item in sources)
        if isinstance(sources, list)
        else str(sources)
    )
    weights = payload.get("weights", config_module.DEFAULT_SOURCE_WEIGHTS)
    weight_text = (
        ", ".join(
            f"{key}={value}"
            for key, value in weights.items()
        )
        if isinstance(weights, dict)
        else str(weights)
    )
    fingerprint_retrieval = payload.get("fingerprint_retrieval", {})
    spectral_analysis = payload.get("spectral_analysis", {})
    rows: list[list[object]] = [
        ["Audio Dedup Report", "", "", "", ""],
        [
            "Review workbook before deleting files. Report mode is read-only; apply mode deletes only safe candidates after exact confirmation.",
            "",
            "",
            "",
            "",
        ],
        [],
        ["Run settings", "Value", "Notes", "", ""],
        ["Generated at", payload["generated_at"], "Local timestamp when this report was written.", "", ""],
        ["Database", payload.get("database_path") or "", "SQLite library that was read for track metadata and embeddings.", "", ""],
        ["Root", payload["root"], "Only stored track paths inside this root were considered.", "", ""],
        ["Path filter", path_filter or "(none)", "Optional case-insensitive path substring filters.", "", ""],
        ["Mode", payload.get("mode", "report-only"), "Report-only writes evidence and does not delete audio.", "", ""],
        ["Search mode", payload.get("search_mode", ""), "fingerprint: exact SONARA matches decide duplicates, everything stays manual-review. embedding: weighted embedding score decides and can mark safe delete candidates.", "", ""],
        ["Preset", payload["preset"], "safe is conservative; balanced/aggressive widen review scope.", "", ""],
        ["Sources", source_text, "Enabled audio embedding families.", "", ""],
        ["Source weights", weight_text, "Raw weights are renormalized over available enabled evidence.", "", ""],
        ["Min score", payload["min_score"], "Overall duplicate score threshold.", "", ""],
        ["Min content similarity", payload["min_similarity"], "Audio-to-audio embedding gate over enabled MERT, MAEST, MuQ, and CLAP sources; not CLAP text-search score.", "", ""],
        ["Fingerprint review threshold", fingerprint_retrieval.get("fingerprint_review_min_similarity", "") if isinstance(fingerprint_retrieval, dict) else "", "Exact SONARA scores at or above this threshold add manual-review candidates only.", "", ""],
        [],
        ["Decision summary", "Count", "Meaning", "Next action", ""],
        [
            "Total tracks in database",
            payload.get("database_track_count", payload["track_count"]),
            "All tracks currently stored in the selected SQLite database.",
            "Reference only.",
            "",
        ],
        [
            "Tracks inside selected root",
            payload.get("scoped_track_count", payload["track_count"]),
            "Tracks that matched root and optional path filters.",
            "This is the search scope.",
            "",
        ],
        ["Duplicate groups", payload["group_count"], "Potential duplicate clusters found.", "Open the Groups sheet.", ""],
        ["Duplicate candidates", stats.get("candidate_count", 0), "Tracks proposed for delete or manual review.", "Open the Candidates sheet.", ""],
        ["Valid stored fingerprints", fingerprint_retrieval.get("valid_stored_fingerprint_count", 0) if isinstance(fingerprint_retrieval, dict) else 0, "Identity-bound SONARA fingerprints used for independent LSH retrieval.", "Reference only.", ""],
        [
            "Suspected transcodes in groups",
            spectral_analysis.get("suspected_transcode_count", 0) if isinstance(spectral_analysis, dict) else 0,
            "Group members whose spectrum ends in a brickwall below 20 kHz (fake-bitrate evidence).",
            "Keeper choice already prefers full-band copies; confirm by ear.",
            "",
        ],
        [
            "Fake-bitrate duplicate candidates",
            stats.get("fake_bitrate_candidate_count", 0),
            (
                "Duplicate copies (not the keeper) that look transcoded, across "
                f"{stats.get('fake_bitrate_group_count', 0)} group(s)."
            ),
            "Open the Groups sheet; those rows are highlighted amber.",
            "",
        ],
        [
            "Spectral checks",
            (
                f"{spectral_analysis.get('analyzed_track_count', 0)}/{spectral_analysis.get('checked_track_count', 0)}"
                if isinstance(spectral_analysis, dict)
                else ""
            ),
            "Duplicate-group files with a measured frequency cutoff.",
            "Unreachable files and decode errors are skipped, never guessed.",
            "",
        ],
        ["Fingerprint review pairs", fingerprint_retrieval.get("fingerprint_review_pair_count", 0) if isinstance(fingerprint_retrieval, dict) else 0, "Exact SONARA matches that met the review threshold.", "Open Pair Evidence.", ""],
        [
            "Safe delete candidates",
            stats.get("safe_candidate_count", 0),
            "Direct high-confidence matches to the suggested keeper.",
            "Open the Candidates sheet and review every row before apply mode.",
            "",
        ],
        [
            "Manual review candidates",
            stats.get("review_candidate_count", 0),
            "Candidates with blockers or weaker evidence.",
            "Do not delete automatically.",
            "",
        ],
    ]
    if isinstance(rhythm_lab, dict):
        rows.extend(
            [
                [],
                ["Rhythm Lab impact", "Value", "Meaning", "", ""],
                ["Database", rhythm_lab.get("database_path", ""), "Lab database checked for labels/predictions on safe candidates.", "", ""],
                ["Database exists", rhythm_lab.get("database_exists", False), "False means no lab rows can be affected.", "", ""],
                ["Affected tracks on apply", rhythm_lab.get("affected_track_count", 0), "Safe candidates with lab rows.", "", ""],
                ["Affected rows on apply", rhythm_lab.get("affected_row_count", 0), "Rows that apply mode would remove after audio deletion.", "", ""],
            ]
        )
    rows.extend(
        [
            [],
            ["Confidence breakdown", "Groups", "Meaning", "", ""],
        ]
    )
    if isinstance(confidence, dict):
        meanings = {
            "high": "Score is strong and has no major blockers.",
            "medium": "Likely duplicate, but review evidence before deletion.",
            "review": "Needs manual inspection.",
        }
        for label in ("high", "medium", "review"):
            rows.append([label, confidence.get(label, 0), meanings[label], "", ""])
    rows.extend([[], ["Embeddings loaded (this run)", "Tracks", "Meaning", "", ""]])
    if isinstance(embeddings, dict):
        for label in config_module.SUPPORTED_EMBEDDINGS:
            rows.append([label.upper(), embeddings.get(label, 0), "Vectors loaded for this run's scoring; 0 when the family was not selected (always 0 in fingerprint mode).", "", ""])
    semantics = payload.get("score_semantics", {})
    if isinstance(semantics, dict):
        rows.extend([[], ["Score semantics", "Kind", "Range", "Notes", ""]])
        for key in (
            "score",
            "content_similarity",
            "mert_similarity",
            "maest_similarity",
            "muq_similarity",
            "clap_similarity",
            "fingerprint_similarity",
        ):
            item = semantics.get(key, {})
            if isinstance(item, dict):
                rows.append([key, item.get("kind", ""), item.get("range", ""), item.get("notes", ""), ""])
    return rows


GROUPS_SHEET_FAKE_BITRATE_COLUMN_INDEX = 8


def _groups_sheet_rows(payload: dict[str, object]) -> list[list[object]]:
    rows: list[list[object]] = [
        [
            "group_id",
            "confidence",
            "score",
            "keeper_track_id",
            "keeper_path",
            "candidate_count",
            "safe_candidates",
            "review_candidates",
            "fake_bitrate_candidates",
            "why_keep",
            "blocked_reasons",
        ]
    ]
    assert rows[0][GROUPS_SHEET_FAKE_BITRATE_COLUMN_INDEX] == "fake_bitrate_candidates"
    for group in payload["groups"]:  # type: ignore[index]
        assert isinstance(group, dict)
        keeper = group["suggested_keeper"]
        assert isinstance(keeper, dict)
        candidates = [candidate for candidate in group["candidate_deletes"] if isinstance(candidate, dict)]  # type: ignore[index]
        rows.append(
            [
                group["group_id"],
                group["confidence"],
                group["score"],
                keeper["track_id"],
                keeper["path"],
                len(candidates),
                sum(1 for candidate in candidates if candidate.get("decision") == "delete_candidate"),
                sum(1 for candidate in candidates if candidate.get("decision") != "delete_candidate"),
                sum(1 for candidate in candidates if candidate.get("suspected_transcode")),
                "; ".join(str(item) for item in keeper.get("why_keep", [])),
                "; ".join(str(item) for item in group.get("blocked_reasons", [])),
            ]
        )
    return rows


CANDIDATES_SHEET_SUSPECTED_TRANSCODE_COLUMN = 10
CANDIDATES_SHEET_KEEPER_SUSPECTED_TRANSCODE_COLUMN = 12


def _candidates_sheet_rows(payload: dict[str, object]) -> list[list[object]]:
    rows: list[list[object]] = [
        [
            "group_id",
            "action",
            "delete_track_id",
            "delete_path",
            "keeper_track_id",
            "keeper_path",
            "score_vs_keeper",
            "content_similarity_vs_keeper",
            "safe_to_delete",
            "suspected_transcode",
            "spectral_note",
            "keeper_suspected_transcode",
            "keeper_spectral_note",
            "mert_similarity",
            "maest_similarity",
            "muq_similarity",
            "sonara_similarity",
            "fingerprint_similarity",
            "clap_similarity",
            "duration_diff_seconds",
            "duration_diff_ratio",
            "blocked_reasons",
            "why_delete_or_review",
        ]
    ]
    assert rows[0][CANDIDATES_SHEET_SUSPECTED_TRANSCODE_COLUMN - 1] == "suspected_transcode"
    assert rows[0][CANDIDATES_SHEET_KEEPER_SUSPECTED_TRANSCODE_COLUMN - 1] == "keeper_suspected_transcode"
    for group in payload["groups"]:  # type: ignore[index]
        assert isinstance(group, dict)
        keeper = group["suggested_keeper"]
        assert isinstance(keeper, dict)
        evidence_by_candidate = _evidence_by_candidate(group, int(keeper["track_id"]))
        for candidate in group["candidate_deletes"]:  # type: ignore[index]
            assert isinstance(candidate, dict)
            evidence = evidence_by_candidate.get(int(candidate["track_id"]), {})
            rows.append(
                [
                    group["group_id"],
                    candidate["action"],
                    candidate["track_id"],
                    candidate["path"],
                    keeper["track_id"],
                    keeper["path"],
                    candidate["score_vs_keeper"],
                    candidate.get("content_similarity_vs_keeper"),
                    candidate["safe_to_delete"],
                    candidate.get("suspected_transcode"),
                    candidate.get("spectral_note"),
                    keeper.get("suspected_transcode"),
                    keeper.get("spectral_note"),
                    evidence.get("mert_similarity"),
                    evidence.get("maest_similarity"),
                    evidence.get("muq_similarity"),
                    evidence.get("sonara_similarity"),
                    evidence.get("fingerprint_similarity"),
                    evidence.get("clap_similarity"),
                    evidence.get("duration_diff_seconds"),
                    evidence.get("duration_diff_ratio"),
                    "; ".join(str(item) for item in candidate.get("blocked_reasons", [])),
                    "; ".join(str(item) for item in candidate.get("why_delete_or_review", [])),
                ]
            )
    return rows


def _pair_evidence_sheet_rows(payload: dict[str, object]) -> list[list[object]]:
    rows: list[list[object]] = [
        [
            "group_id",
            "left_track_id",
            "right_track_id",
            "score",
            "content_similarity",
            "mert_similarity",
            "maest_similarity",
            "muq_similarity",
            "sonara_similarity",
            "fingerprint_similarity",
            "clap_similarity",
            "candidate_sources",
            "duration_diff_seconds",
            "duration_diff_ratio",
            "blocked_reasons",
        ]
    ]
    for group in payload["groups"]:  # type: ignore[index]
        assert isinstance(group, dict)
        for evidence in group["pairwise_evidence"]:  # type: ignore[index]
            assert isinstance(evidence, dict)
            rows.append(
                [
                    group["group_id"],
                    evidence["left_track_id"],
                    evidence["right_track_id"],
                    evidence["score"],
                    evidence["content_similarity"],
                    evidence["mert_similarity"],
                    evidence["maest_similarity"],
                    evidence["muq_similarity"],
                    evidence["sonara_similarity"],
                    evidence.get("fingerprint_similarity"),
                    evidence["clap_similarity"],
                    "; ".join(str(item) for item in evidence.get("candidate_sources", [])),
                    evidence["duration_diff_seconds"],
                    evidence["duration_diff_ratio"],
                    "; ".join(str(item) for item in evidence.get("blocked_reasons", [])),
                ]
            )
    return rows


def _rhythm_lab_sheet_rows(payload: dict[str, object]) -> list[list[object]]:
    rows: list[list[object]] = [
        [
            "action",
            "catalog_uuid",
            "track_uuid",
            "table_name",
            "classifier_key",
            "label",
            "path",
            "feature_set",
            "model_artifact",
            "confidence",
        ]
    ]
    rhythm_lab = payload.get("rhythm_lab", {})
    if not isinstance(rhythm_lab, dict):
        return rows
    for row in rhythm_lab.get("affected_rows", []):
        if not isinstance(row, dict):
            continue
        rows.append(
            [
                row.get("action", ""),
                row.get("catalog_uuid", ""),
                row.get("track_uuid", ""),
                row.get("table_name", ""),
                row.get("classifier_key", ""),
                row.get("label", ""),
                row.get("path", ""),
                row.get("feature_set", ""),
                row.get("model_artifact", ""),
                row.get("confidence", ""),
            ]
        )
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
<dc:title>Audio dedup report</dc:title>
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
<fonts count="8">
<font><sz val="11"/><color rgb="FF111827"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><b/><sz val="18"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FF1B5E20"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FFB71C1C"/><name val="Calibri"/></font>
<font><sz val="11"/><color rgb="FF374151"/><name val="Calibri"/></font>
<font><b/><sz val="12"/><color rgb="FF111827"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="FF92400E"/><name val="Calibri"/></font>
</fonts>
<fills count="11">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF263238"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE8F5E9"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFEBEE"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE3F2FD"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FF111827"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFF3F4F6"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFE0F2FE"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFFF7ED"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFFEF3C7"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left style="thin"><color rgb="FFD1D5DB"/></left><right style="thin"><color rgb="FFD1D5DB"/></right><top style="thin"><color rgb="FFD1D5DB"/></top><bottom style="thin"><color rgb="FFD1D5DB"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="11">
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="2" fillId="6" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="3" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="4" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
<xf numFmtId="0" fontId="5" fillId="7" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
<xf numFmtId="0" fontId="6" fillId="8" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment wrapText="1" vertical="center"/></xf>
<xf numFmtId="0" fontId="0" fillId="9" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
<xf numFmtId="0" fontId="0" fillId="7" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
<xf numFmtId="0" fontId="7" fillId="10" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>'''


def _xlsx_sheet_xml(name: str, rows: list[list[object]]) -> str:
    max_cols = max((len(row) for row in rows), default=1)
    if name == "Summary":
        max_cols = max(5, max_cols)
    col_widths = _xlsx_column_widths(rows, max_cols, sheet_name=name)
    cols_xml = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(col_widths, start=1)
    )
    sheet_views = ""
    if name == "Summary":
        sheet_views = '<sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane ySplit="3" topLeftCell="A4" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
    elif len(rows) > 1:
        sheet_views = '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
    rows_xml = "\n".join(_xlsx_row_xml(row, row_index, name) for row_index, row in enumerate(rows, start=1))
    dimension = f"A1:{_xlsx_col_name(max_cols)}{max(1, len(rows))}"
    auto_filter = f'<autoFilter ref="A1:{_xlsx_col_name(max_cols)}1"/>' if name != "Summary" and len(rows) > 1 else ""
    merge_cells = ""
    if name == "Summary":
        merge_cells = '<mergeCells count="2"><mergeCell ref="A1:E1"/><mergeCell ref="A2:E2"/></mergeCells>'
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<dimension ref="{dimension}"/>
{sheet_views}
<cols>{cols_xml}</cols>
<sheetData>
{rows_xml}
</sheetData>
{merge_cells}
{auto_filter}
</worksheet>'''


def _xlsx_row_xml(row: list[object], row_index: int, sheet_name: str) -> str:
    if sheet_name == "Summary" and row_index == 1:
        height = ' ht="32" customHeight="1"'
    elif sheet_name == "Summary" and row_index == 2:
        height = ' ht="40" customHeight="1"'
    else:
        height = ' ht="26" customHeight="1"' if row_index == 1 else ""
    cells = "".join(
        _xlsx_cell_xml(value, row_index, col_index, _xlsx_style_id(value, row, row_index, col_index, sheet_name))
        for col_index, value in enumerate(row, start=1)
    )
    return f'<row r="{row_index}"{height}>{cells}</row>'


_EXCEL_CELL_TEXT_LIMIT = 32767
_XLSX_ILLEGAL_TEXT = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def _xml_safe_text(value: str) -> str:
    return _XLSX_ILLEGAL_TEXT.sub("", value)[:_EXCEL_CELL_TEXT_LIMIT]


def _xlsx_cell_xml(value: object, row_index: int, col_index: int, style_id: int) -> str:
    ref = f"{_xlsx_col_name(col_index)}{row_index}"
    style = f' s="{style_id}"'
    if value is None:
        return f'<c r="{ref}"{style}/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"{style}><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return f'<c r="{ref}"{style}/>'
        return f'<c r="{ref}"{style}><v>{value}</v></c>'
    text = escape(_xml_safe_text(str(value)))
    return f'<c r="{ref}" t="inlineStr"{style}><is><t>{text}</t></is></c>'


def _xlsx_style_id(value: object, row: list[object], row_index: int, col_index: int, sheet_name: str) -> int:
    if sheet_name == "Summary":
        first = str(row[0]) if row else ""
        if row_index == 1:
            return 2
        if row_index == 2:
            return 6
        if first in {"Run settings", "Decision summary", "Rhythm Lab impact", "Confidence breakdown", "Embedding coverage"}:
            return 7
        if first == "Safe delete candidates":
            return 3
        if first == "Manual review candidates":
            return 4
        if first == "Mode" and str(row[1] if len(row) > 1 else "") == "apply":
            return 8
        return 9 if col_index in {3, 4} else 5
    if row_index == 1 and sheet_name == "Summary":
        return 2
    if row_index == 1:
        return 1
    if sheet_name == "Groups":
        fake_bitrate_count = row[GROUPS_SHEET_FAKE_BITRATE_COLUMN_INDEX] if len(row) > GROUPS_SHEET_FAKE_BITRATE_COLUMN_INDEX else 0
        if isinstance(fake_bitrate_count, (int, float)) and fake_bitrate_count > 0:
            return 10
        return 5
    if value == "DELETE CANDIDATE":
        return 3
    if value == "REVIEW MANUALLY":
        return 4
    if sheet_name == "Candidates" and value is True and col_index in {CANDIDATES_SHEET_SUSPECTED_TRANSCODE_COLUMN, CANDIDATES_SHEET_KEEPER_SUSPECTED_TRANSCODE_COLUMN}:
        return 10
    return 5


def _xlsx_column_widths(rows: list[list[object]], max_cols: int, *, sheet_name: str) -> list[int]:
    if sheet_name == "Summary":
        return [28, 24, 54, 44, 14][:max_cols]
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


def _evidence_by_candidate(group: dict[str, object], keeper_id: int) -> dict[int, dict[str, object]]:
    result: dict[int, dict[str, object]] = {}
    for item in group["pairwise_evidence"]:  # type: ignore[index]
        assert isinstance(item, dict)
        left = int(item["left_track_id"])
        right = int(item["right_track_id"])
        if left == keeper_id:
            result[right] = item
        elif right == keeper_id:
            result[left] = item
    return result
