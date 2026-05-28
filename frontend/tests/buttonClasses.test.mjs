import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import test from "node:test";

const srcDir = fileURLToPath(new URL("../src", import.meta.url));
const styleTokens = new Set([
  "active",
  "icon-button",
  "intent-add",
  "intent-remove",
  "primary",
  "secondary-mini"
]);

function sourceFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return entry.isFile() && /\.(tsx|jsx)$/.test(entry.name) ? [path] : [];
  });
}

function buttonTags(source) {
  return source.match(/<button\b[\s\S]*?>/g) || [];
}

function classNameValue(tag) {
  const start = tag.indexOf("className=");
  if (start === -1) return "";
  const valueStart = start + "className=".length;
  const opener = tag[valueStart];
  if (opener === '"' || opener === "'") {
    const end = tag.indexOf(opener, valueStart + 1);
    return tag.slice(valueStart + 1, end);
  }
  if (opener !== "{") return "";
  let depth = 0;
  for (let index = valueStart; index < tag.length; index += 1) {
    if (tag[index] === "{") depth += 1;
    if (tag[index] === "}") {
      depth -= 1;
      if (depth === 0) return tag.slice(valueStart + 1, index);
    }
  }
  return "";
}

function semanticClassTokens(value) {
  return (value.match(/[A-Za-z][A-Za-z0-9_-]*/g) || [])
    .filter((token) => !styleTokens.has(token))
    .filter((token) => /(?:button|tab|chip)$/.test(token));
}

test("every button has a semantic class name", () => {
  const failures = [];
  for (const file of sourceFiles(srcDir)) {
    const source = readFileSync(file, "utf8");
    if (!statSync(file).isFile()) continue;
    for (const tag of buttonTags(source)) {
      const className = classNameValue(tag);
      const semantics = semanticClassTokens(className);
      if (!className || semantics.length === 0) {
        failures.push(`${file}: ${tag.replace(/\s+/g, " ")}`);
      }
    }
  }
  assert.deepEqual(failures, []);
});

test("every button exposes tooltip text", () => {
  const failures = [];
  for (const file of sourceFiles(srcDir)) {
    const source = readFileSync(file, "utf8");
    if (!statSync(file).isFile()) continue;
    for (const tag of buttonTags(source)) {
      if (!/\btitle=/.test(tag)) {
        failures.push(`${file}: ${tag.replace(/\s+/g, " ")}`);
      }
    }
  }
  assert.deepEqual(failures, []);
});

test("button tooltip text uses compact viewport-level styling", () => {
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");
  const rule = styles.match(/\.ui-tooltip\s*{([\s\S]*?)}/)?.[1] || "";

  assert.doesNotMatch(styles, /\.app-shell\s+\[title\][^{]*::after/);
  assert.match(rule, /position:\s*fixed/);
  assert.match(rule, /font-size:\s*12px/);
  assert.match(rule, /line-height:\s*1\.25/);
  assert.match(rule, /max-width:\s*min\(260px,\s*calc\(100vw - 16px\)\)/);
  assert.match(rule, /overflow-wrap:\s*anywhere/);
});

test("genre save button is placed between refresh tags and database clear", () => {
  const source = readFileSync(join(srcDir, "LibraryPanel.tsx"), "utf8");

  const refreshIndex = source.indexOf("refresh-tags-button");
  const genreSaveIndex = source.indexOf("genre-save-button");
  const clearIndex = source.indexOf("database-clear-button");

  assert.notEqual(refreshIndex, -1);
  assert.notEqual(genreSaveIndex, -1);
  assert.notEqual(clearIndex, -1);
  assert.ok(refreshIndex < genreSaveIndex);
  assert.ok(genreSaveIndex < clearIndex);
});

test("scan action row reserves one line for all scan controls", () => {
  const source = readFileSync(join(srcDir, "LibraryPanel.tsx"), "utf8");
  const styles = readFileSync(join(srcDir, "styles.css"), "utf8");
  const rowMatch = source.match(/<div className="scan-action-row">([\s\S]*?)<\/div>/);
  const styleMatch = styles.match(/\.scan-action-row\s*{([\s\S]*?)}/);

  assert.ok(rowMatch, "scan action row markup exists");
  assert.ok(styleMatch, "scan action row styles exist");

  const controlCount = (rowMatch[1].match(/<button\b/g) || []).length;
  const declaredIconColumns = Number(styleMatch[1].match(/repeat\((\d+),\s*42px\)/)?.[1] || 0);

  assert.equal(controlCount, 4);
  assert.equal(declaredIconColumns, controlCount - 1);
});
