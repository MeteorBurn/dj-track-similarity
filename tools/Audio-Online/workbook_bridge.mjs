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
  const fields = contract.primary_fields;
  let row = 0;
  for (const block of contract.tracks) {
    sheet.getRangeByIndexes(row, 0, 1, columns.length).merge();
    sheet.getCell(row, 0).values = [[block.track_name]];
    sheet.getRangeByIndexes(row, 0, 1, columns.length).format = { fill: "#1F2937", font: { bold: true, color: "#FFFFFF" } };
    row += 1;
    sheet.getRangeByIndexes(row, 0, 1, columns.length).values = [columns];
    sheet.getRangeByIndexes(row, 0, 1, columns.length).format = { fill: "#334155", font: { bold: true, color: "#FFFFFF" } };
    row += 1;
    for (const field of fields) {
      const values = [field, ...columns.slice(1).map((name) => block.rows[field]?.[name] ?? "")];
      sheet.getRangeByIndexes(row, 0, 1, columns.length).values = [values];
      if (["Genre", "Style", "Tags"].includes(field)) sheet.getRangeByIndexes(row, 0, 1, columns.length).format = { fill: "#E8F4ED" };
      row += 1;
    }
    row += 1;
  }
  sheet.freezePanes.freezeRows(2);
  sheet.freezePanes.freezeColumns(1);
  sheet.getUsedRange().format.wrapText = true;
  sheet.getUsedRange().format.autofitColumns();
  const used = sheet.getUsedRange();
  used.getColumn(0).format.columnWidth = 20;
  for (let column = 1; column < columns.length; column += 1) used.getColumn(column).format.columnWidth = 27;
  return workbook;
}

async function main() {
  const [, , command, input, output] = process.argv;
  if (!input || !output) throw new Error("usage: workbook_bridge.mjs <write|read> <input> <output>");
  if (command === "read") {
    const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(input));
    const sheet = workbook.worksheets.getActiveWorksheet();
    const values = sheet.getUsedRange().values;
    const headers = values.shift().map((value) => String(value ?? "").trim());
    const rows = values.filter((row) => row.some((value) => value !== null && value !== "")).map((row) => Object.fromEntries(headers.map((header, index) => [header, row[index] == null ? "" : String(row[index])] )));
    await fs.writeFile(output, JSON.stringify(rows), "utf8");
    return;
  }
  if (command !== "write") throw new Error("usage: workbook_bridge.mjs <write|read> <input> <output>");
  const contract = JSON.parse(await fs.readFile(input, "utf8"));
  const workbook = await buildWorkbook(contract);
  const file = await SpreadsheetFile.exportXlsx(workbook);
  await file.save(output);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
