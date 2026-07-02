import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const docsRoot = path.resolve(scriptDir, "..");
const repoRoot = path.resolve(docsRoot, "..", "..");
const valeConfig = path.join(repoRoot, ".vale.ini");
const skippedDirs = new Set(["node_modules", "site", ".vitepress"]);
const baseValeArgs = ["--config", valeConfig, "--no-global", "--no-wrap"];

function resolveVale() {
  const candidates = [
    process.env.VALE_EXE,
    "vale",
    process.platform === "win32" ? "C:\\Utils\\tools\\vale\\vale.exe" : undefined
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (path.isAbsolute(candidate) && !fs.existsSync(candidate)) {
      continue;
    }

    const probe = spawnSync(candidate, ["--version"], { encoding: "utf8" });
    if (!probe.error && probe.status === 0) {
      return candidate;
    }
  }

  throw new Error(
    "Vale was not found. Install Vale, set VALE_EXE, or place vale.exe at C:\\Utils\\tools\\vale\\vale.exe."
  );
}

function collectMarkdownFiles(root) {
  const files = [];

  function walk(current) {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if (!skippedDirs.has(entry.name)) {
          walk(path.join(current, entry.name));
        }
        continue;
      }

      if (entry.isFile() && entry.name.endsWith(".md")) {
        files.push(toValePath(path.join(current, entry.name)));
      }
    }
  }

  walk(root);
  return files.sort();
}

function runVale(args) {
  const vale = resolveVale();
  const result = spawnSync(vale, args, { cwd: repoRoot, stdio: "inherit" });
  if (result.error) {
    throw result.error;
  }
  process.exit(result.status ?? 1);
}

function toValePath(filePath) {
  return path.relative(repoRoot, filePath).split(path.sep).join("/");
}

const command = process.argv[2] ?? "report";
const markdownFiles = ["README.md", ...collectMarkdownFiles(docsRoot)];

if (command === "sync") {
  runVale([...baseValeArgs, "sync"]);
} else if (command === "report") {
  runVale([...baseValeArgs, "--no-exit", ...markdownFiles]);
} else if (command === "strict") {
  runVale([...baseValeArgs, ...markdownFiles]);
} else {
  throw new Error(`Unknown Vale command: ${command}`);
}
