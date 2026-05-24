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
