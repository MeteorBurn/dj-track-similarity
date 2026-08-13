import assert from "node:assert/strict";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { execFile as execFileCallback } from "node:child_process";
import { promisify } from "node:util";
import test from "node:test";
import { buildWorkbook } from "./workbook_bridge.mjs";

const execFile = promisify(execFileCallback);
const require = createRequire(import.meta.url);
const artifactToolPath = require.resolve("@oai/artifact-tool", { paths: [process.env.METADATA_ENRICHMENT_NODE_MODULES] });
const { SpreadsheetFile, Workbook } = await import(new URL(`file://${artifactToolPath.replaceAll("\\", "/")}`).href);

test("writer creates one flat Metadata table with MAEST last", async () => {
  const workbook = await buildWorkbook({
    sheet: "Metadata", columns: ["Track Name", "Local Genre", "Discogs Genre", "MAEST"],
    rows: [{ "Track Name": "Artist — Title", "Local Genre": "Electronic", "Discogs Genre": "Melodic Techno", MAEST: "House (81%); Techno (64%); Electronic (52%)" }],
  });
  assert.deepEqual(workbook.worksheets.items.map((sheet) => sheet.name), ["Metadata"]);
  assert.equal(workbook.worksheets.getItem("Metadata").getRange("D2").values[0][0], "House (81%); Techno (64%); Electronic (52%)");
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), "audio-online-"));
  const input = path.join(temp, "contract.json");
  const output = path.join(temp, "metadata.xlsx");
  await fs.writeFile(input, JSON.stringify({ sheet: "Metadata", columns: ["Track Name", "Local Genre", "Discogs Genre", "MAEST"], rows: [{ "Track Name": "Artist — Title", "Local Genre": "Electronic", "Discogs Genre": "Melodic Techno", MAEST: "House (81%); Techno (64%); Electronic (52%)" }] }));
  await execFile(process.execPath, [fileURLToPath(new URL("./workbook_bridge.mjs", import.meta.url)), "write", input, output]);
  assert.ok((await fs.stat(output)).size > 0);
});

test("reader extracts common input columns from XLSX", async () => {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), "audio-online-input-"));
  const input = path.join(temp, "tracks.xlsx");
  const output = path.join(temp, "rows.json");
  const workbook = Workbook.create();
  const sheet = workbook.worksheets.add("Tracks");
  sheet.getRange("A1:F2").values = [["Artist", "Title", "Album", "Year", "Country", "Label"], ["Artist", "Title", "Release", 2024, "Germany", "Label"]];
  await (await SpreadsheetFile.exportXlsx(workbook)).save(input);

  await execFile(process.execPath, [fileURLToPath(new URL("./workbook_bridge.mjs", import.meta.url)), "read", input, output]);

  assert.deepEqual(JSON.parse(await fs.readFile(output, "utf8")), [{ Artist: "Artist", Title: "Title", Album: "Release", Year: "2024", Country: "Germany", Label: "Label" }]);
});
