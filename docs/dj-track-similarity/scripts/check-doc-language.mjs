/*
 * Documentation language gate.
 *
 * The browser interface is Russian; the documentation is English. Pages name
 * every control by its English name and link to the glossary when a reader
 * needs the on-screen string. `help/ui-language.md` is the one page that holds
 * Russian, because mapping Russian to English is its whole job.
 *
 * This check fails when Cyrillic reaches any other maintained page.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const docsRoot = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(docsRoot, "..", "..");

const skippedDirs = new Set(["node_modules", "site", ".vitepress"]);

// The glossary exists to print the Russian interface strings beside their
// English meaning. Every other maintained page stays English.
const allowedFiles = new Set([path.join(docsRoot, "help", "ui-language.md")]);

// Documentation that lives outside the VitePress tree. Every one of these is
// English, so the gate covers them the same way it covers the pages.
const extraRoots = [
  path.join(repoRoot, "README.md"),
  path.join(repoRoot, "docs", "README.md"),
  path.join(repoRoot, "tools", "audio-dedup", "README.md"),
  path.join(repoRoot, "tools", "audio-doctor", "README.md"),
  path.join(repoRoot, "tools", "audio-online", "README.md"),
  path.join(repoRoot, "tools", "rhythm-lab", "README.md")
];

const cyrillic = /[Ѐ-ӿԀ-ԯ]/;

function collectMarkdownFiles(root) {
  const files = [];

  function walk(current) {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) {
        if (!skippedDirs.has(entry.name)) {
          walk(full);
        }
        continue;
      }
      if (entry.isFile() && entry.name.endsWith(".md")) {
        files.push(full);
      }
    }
  }

  walk(root);
  return files.sort();
}

const files = [...collectMarkdownFiles(docsRoot), ...extraRoots.filter((f) => fs.existsSync(f))];

const findings = [];
for (const file of files) {
  if (allowedFiles.has(file)) {
    continue;
  }

  const lines = fs.readFileSync(file, "utf8").split(/\r?\n/);
  lines.forEach((line, index) => {
    if (cyrillic.test(line)) {
      findings.push({
        file: path.relative(repoRoot, file).split(path.sep).join("/"),
        line: index + 1,
        text: line.trim()
      });
    }
  });
}

if (findings.length === 0) {
  console.log(`Documentation language check passed: ${files.length} files, no Cyrillic outside the glossary.`);
  process.exit(0);
}

console.error(`Documentation language check failed: ${findings.length} line(s) carry Cyrillic.`);
console.error("");
console.error("The documentation is English. Name the control by its English name and link to");
console.error("docs/dj-track-similarity/help/ui-language.md when the reader needs the Russian");
console.error("string that the interface actually shows.");
console.error("");
for (const finding of findings) {
  console.error(`  ${finding.file}:${finding.line}: ${finding.text.slice(0, 160)}`);
}
process.exit(1);
