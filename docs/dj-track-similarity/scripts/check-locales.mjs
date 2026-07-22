import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const docsRoot = path.resolve(scriptDir, "..");
const russianRoot = path.join(docsRoot, "ru");
const vitePressConfig = path.join(docsRoot, ".vitepress", "config.mts");
const skippedDirs = new Set([".vitepress", "node_modules", "ru", "scripts", "site"]);

function collectMarkdown(root, { skipTopLevel = false } = {}) {
  const files = [];

  function walk(current, depth) {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        if ((skipTopLevel && depth === 0 && skippedDirs.has(entry.name)) || entry.name === "site") {
          continue;
        }
        walk(path.join(current, entry.name), depth + 1);
      } else if (entry.isFile() && entry.name.endsWith(".md")) {
        files.push(path.relative(root, path.join(current, entry.name)).split(path.sep).join("/"));
      }
    }
  }

  walk(root, 0);
  return files.sort();
}

function extractFences(markdown) {
  return [...markdown.matchAll(/^```([^\r\n]*)\r?\n([\s\S]*?)^```\s*$/gm)].map((match) => ({
    info: match[1].trim().toLowerCase(),
    body: match[2].replaceAll("\r\n", "\n")
  }));
}

function withoutFences(markdown) {
  return markdown.replace(/^```[^\r\n]*\r?\n[\s\S]*?^```\s*$/gm, "");
}

function extractInlineCode(markdown) {
  return [...withoutFences(markdown).matchAll(/(?<!`)`([^`\r\n]+)`(?!`)/g)]
    .map((match) => match[1]);
}

function extractHeadingLevels(markdown) {
  return [...withoutFences(markdown).matchAll(/^(#{1,6})\s+\S/gm)]
    .map((match) => match[1].length);
}

function extractLinkTargets(markdown) {
  const source = withoutFences(markdown);
  const markdownTargets = [...source.matchAll(/!?\[[^\]]*\]\(([^)\s]+)(?:\s+["'][^"']*["'])?\)/g)].map((match) => match[1]);
  const htmlTargets = [...source.matchAll(/\b(?:href|src)=["']([^"']+)["']/g)].map((match) => match[1]);
  return [...markdownTargets, ...htmlTargets];
}

function extractNumbers(markdown) {
  return [...withoutFences(markdown).matchAll(/(?<![\p{L}\p{N}_])[vV]?[-+]?\d+(?:[.,]\d+)*(?:%|x|kHz|Hz|k)?(?![\p{L}\p{N}_])/gu)]
    .map((match) => match[0]);
}

function extractProtectedFenceTokens(body) {
  return [...body.matchAll(/\b(?:[A-Z][A-Z0-9]{1,}|Typer|LibraryDatabase|FastAPI|React|SONARA|Symphonia|FFmpeg|Rhythm Lab|Hybrid)\b/g)]
    .map((match) => match[0]);
}

function normalizeMermaidStructure(body) {
  return body.replace(/\[[^\]\r\n]*\]/g, "[]");
}

function sameFences(left, right) {
  if (left.length !== right.length) return false;

  return left.every((englishFence, index) => {
    const russianFence = right[index];
    if (englishFence.info !== russianFence.info) return false;

    if (englishFence.info === "mermaid") {
      return /[А-Яа-яЁё]/u.test(russianFence.body)
        && normalizeMermaidStructure(englishFence.body) === normalizeMermaidStructure(russianFence.body)
        && sameArray(extractProtectedFenceTokens(englishFence.body), extractProtectedFenceTokens(russianFence.body))
        && sameArray(extractNumbers(englishFence.body), extractNumbers(russianFence.body));
    }

    const isTextWorkflow = englishFence.info === "text" && englishFence.body.includes(" -> ");
    if (isTextWorkflow) {
      const englishArrows = englishFence.body.match(/->/g) || [];
      const russianArrows = russianFence.body.match(/->/g) || [];
      return /[А-Яа-яЁё]/u.test(russianFence.body)
        && englishArrows.length === russianArrows.length
        && sameArray(extractProtectedFenceTokens(englishFence.body), extractProtectedFenceTokens(russianFence.body))
        && sameArray(extractNumbers(englishFence.body), extractNumbers(russianFence.body));
    }

    return englishFence.body === russianFence.body;
  });
}

function extractLongParagraphs(markdown) {
  return withoutFences(markdown)
    .split(/\r?\n\s*\r?\n/)
    .map((paragraph) => paragraph.replace(/\s+/g, " ").trim())
    .filter((paragraph) => (paragraph.match(/[A-Za-zА-Яа-яЁё]/gu) || []).length >= 80);
}

function sameArray(left, right) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function routeFor(relativePath, locale = "") {
  const prefix = locale ? `/${locale}` : "";
  if (relativePath === "index.md") return `${prefix}/` || "/";
  if (relativePath.endsWith("/index.md")) return `${prefix}/${relativePath.slice(0, -8)}`;
  return `${prefix}/${relativePath.slice(0, -3)}.html`;
}

if (!fs.existsSync(russianRoot)) {
  console.error(`Missing Russian locale directory: ${russianRoot}`);
  process.exit(1);
}

const englishFiles = collectMarkdown(docsRoot, { skipTopLevel: true });
const russianFiles = collectMarkdown(russianRoot);
const missing = englishFiles.filter((file) => !russianFiles.includes(file));
const extra = russianFiles.filter((file) => !englishFiles.includes(file));
const errors = [];

if (missing.length) errors.push(`Missing Russian pages:\n  ${missing.join("\n  ")}`);
if (extra.length) errors.push(`Russian pages without an English source:\n  ${extra.join("\n  ")}`);

const configSource = fs.readFileSync(vitePressConfig, "utf8");
const configuredRoutes = new Set(
  [...configSource.matchAll(/\blink:\s*"([^"]+)"/g)]
    .map((match) => match[1])
    .filter((link) => link.startsWith("/"))
);
const derivesRussianSidebar =
  /const\s+russianSidebar[\s\S]*?englishSidebar\.map/.test(configSource) &&
  /link:\s*russianLink\(item\.link\)/.test(configSource);

if (derivesRussianSidebar) {
  for (const route of [...configuredRoutes]) {
    if (!route.startsWith("/ru")) {
      configuredRoutes.add(route === "/" ? "/ru/" : `/ru${route}`);
    }
  }
}
const expectedEnglishRoutes = englishFiles.map((file) => routeFor(file));
const expectedRussianRoutes = englishFiles.map((file) => routeFor(file, "ru"));
const missingEnglishRoutes = expectedEnglishRoutes.filter((route) => !configuredRoutes.has(route));
const missingRussianRoutes = expectedRussianRoutes.filter((route) => !configuredRoutes.has(route));
const knownRoutes = new Set([...expectedEnglishRoutes, ...expectedRussianRoutes]);
const unknownConfiguredRoutes = [...configuredRoutes].filter((route) => !knownRoutes.has(route));

if (missingEnglishRoutes.length) {
  errors.push(`English pages missing from VitePress navigation:\n  ${missingEnglishRoutes.join("\n  ")}`);
}
if (missingRussianRoutes.length) {
  errors.push(`Russian pages missing from VitePress navigation:\n  ${missingRussianRoutes.join("\n  ")}`);
}
if (unknownConfiguredRoutes.length) {
  errors.push(`VitePress navigation routes without a source page:\n  ${unknownConfiguredRoutes.join("\n  ")}`);
}

for (const relativePath of englishFiles.filter((file) => russianFiles.includes(file))) {
  const english = fs.readFileSync(path.join(docsRoot, relativePath), "utf8");
  const russian = fs.readFileSync(path.join(russianRoot, relativePath), "utf8");

  if (!/[А-Яа-яЁё]/u.test(russian)) {
    errors.push(`${relativePath}: Russian page contains no Cyrillic text`);
  }
  if (english === russian) {
    errors.push(`${relativePath}: Russian page is identical to the English source`);
  }
  if (!sameFences(extractFences(english), extractFences(russian))) {
    errors.push(`${relativePath}: fenced blocks differ structurally or executable content changed`);
  }
  if (!sameArray(extractHeadingLevels(english), extractHeadingLevels(russian))) {
    errors.push(`${relativePath}: heading structure differs from the English source`);
  }
  if (!sameArray(extractInlineCode(english), extractInlineCode(russian))) {
    errors.push(`${relativePath}: inline code identifier sequence differs from the English source`);
  }
  if (!sameArray(extractLinkTargets(english), extractLinkTargets(russian))) {
    errors.push(`${relativePath}: link or image target sequence differs from the English source`);
  }
  if (!sameArray(extractNumbers(english), extractNumbers(russian))) {
    errors.push(`${relativePath}: numeric value sequence differs from the English source`);
  }
  const englishParagraphs = new Set(extractLongParagraphs(english));
  const untranslated = extractLongParagraphs(russian).filter((paragraph) => englishParagraphs.has(paragraph));
  if (untranslated.length) {
    errors.push(`${relativePath}: ${untranslated.length} long paragraph(s) remain untranslated`);
  }
}

if (errors.length) {
  console.error(errors.join("\n\n"));
  process.exit(1);
}

console.log(`Russian locale parity OK: ${russianFiles.length}/${englishFiles.length} pages.`);
