import fs from "node:fs/promises";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const packageSearchPath = process.env.METADATA_ENRICHMENT_NODE_MODULES;
if (!packageSearchPath) throw new Error("METADATA_ENRICHMENT_NODE_MODULES must point to the artifact-tool node_modules directory");
const artifactToolPath = require.resolve("@oai/artifact-tool", { paths: [packageSearchPath] });
const { FileBlob, SpreadsheetFile, Workbook } = await import(pathToFileURL(artifactToolPath).href);

export async function buildWorkbook(contract) {
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add(contract.sheet || "Metadata");
  sheet.showGridLines = false;
  const columns = contract.columns;
  sheet.getRangeByIndexes(0, 0, 1, columns.length).values = [columns];
  sheet.getRangeByIndexes(0, 0, 1, columns.length).format = { fill: "#334155", font: { bold: true, color: "#FFFFFF" } };
  const rows = contract.rows || [];
  if (rows.length) {
    const dataRange = sheet.getRangeByIndexes(1, 0, rows.length, columns.length);
    dataRange.values = rows.map((row) => columns.map((column) => String(row[column] ?? "").replaceAll(/\r?\n/g, " ")));
    dataRange.format = { fill: "#FFFFFF", verticalAlignment: "center", wrapText: false, borders: { insideHorizontal: { style: "thin", color: "#E2E8F0" } } };
  }
  for (let column = 0; column < columns.length; column += 1) {
    if (columns[column].endsWith("Genres") || columns[column] === "Tags") {
      sheet.getRangeByIndexes(1, column, rows.length, 1).format = { fill: "#E8F4ED" };
    }
  }
  sheet.freezePanes.freezeRows(1);
  sheet.freezePanes.freezeColumns(1);
  sheet.getUsedRange().format.wrapText = false;
  const used = sheet.getUsedRange();
  used.format.autofitColumns();
  used.getRangeByIndexes(0, 0, 1, columns.length).format.rowHeight = 22;
  if (rows.length) used.getRangeByIndexes(1, 0, rows.length, columns.length).format.rowHeight = 21;
  return workbook;
}

async function main() {
  const [, , command, input, output] = process.argv;
  if (!input || !output) throw new Error("usage: workbook_bridge.mjs <write|read|render> <input> <output>");
  if (command === "read") {
    const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
    const sheet = workbook.worksheets.getActiveWorksheet();
    const values = sheet.getUsedRange().values;
    const headers = values.shift().map((value) => String(value ?? "").trim());
    const rows = values.filter((row) => row.some((value) => value !== null && value !== "")).map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index] == null ? "" : String(row[index])] )));
    await fs.writeFile(output, JSON.stringify(rows), "utf8");
    return;
  }
  if (command === "render") {
    const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
    const preview = await workbook.render({ sheetName: workbook.worksheets.getActiveWorksheet().name, autoCrop: "all", scale: 1, format: "png" });
    await fs.writeFile(output, new Uint8Array(await preview.arrayBuffer()));
    return;
  }
  if (command !== "write") throw new Error("usage: workbook_bridge.mjs <write|read|render> <input> <output>");
  const contract = JSON.parse(await fs.readFile(input, "utf8"));
  const workbook = await buildWorkbook(contract);
  const file = await SpreadsheetFile.exportXlsx(workbook);
  await file.save(output);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
