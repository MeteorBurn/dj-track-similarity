#!/usr/bin/env node
import { mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_URL = "http://127.0.0.1:8765/";
const DEFAULT_LOCATOR = "body";
const DEFAULT_TIMEOUT_MS = 15_000;
const DEFAULT_VIEWPORT = { width: 1440, height: 1000 };

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(scriptDirectory, "..", "..");
const docsRoot = path.join(repositoryRoot, "docs", "dj-track-similarity");
const requireFromDocsPackage = createRequire(path.join(docsRoot, "package.json"));
const { chromium } = requireFromDocsPackage("playwright");
const defaultOutput = path.join(
  repositoryRoot,
  "docs",
  "dj-track-similarity",
  "public",
  "screenshots",
  "locator.png",
);

function printHelp() {
  console.log(`Capture a screenshot of a specific Playwright locator for docs.

Usage:
  npm run docs:screenshot -- -- --locator "text=Search" --output public/screenshots/search.png
  npm run docs:screenshot -- -- --url http://127.0.0.1:8765/ --locator "[data-doc-screenshot='set-builder']"

Options:
  --url <url>          Page URL to open. Default: ${DEFAULT_URL}
  --locator <query>    Playwright locator query to screenshot. Default: ${DEFAULT_LOCATOR}
  --output <path>      PNG path. Relative paths resolve from docs/dj-track-similarity.
                       Default: public/screenshots/locator.png
  --viewport <WxH>     Browser viewport, for example 1440x1000. Default: 1440x1000
  --timeout <ms>       Locator wait timeout in milliseconds. Default: ${DEFAULT_TIMEOUT_MS}
  --html <markup>      Use inline HTML instead of opening --url; intended for smoke tests only.
  --help               Show this help.

The script assumes the UI is already running. It does not start the app or connect to a database.`);
}

function parseArguments(argv) {
  const options = {
    url: DEFAULT_URL,
    locator: DEFAULT_LOCATOR,
    output: defaultOutput,
    timeoutMs: DEFAULT_TIMEOUT_MS,
    viewport: DEFAULT_VIEWPORT,
    html: null,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];

    if (argument === "--help" || argument === "-h") {
      return { help: true, options };
    }

    const nextValue = argv[index + 1];
    if (!argument.startsWith("--")) {
      throw new Error(`Unexpected positional argument: ${argument}`);
    }
    if (!nextValue || nextValue.startsWith("--")) {
      throw new Error(`Missing value for ${argument}`);
    }

    index += 1;

    if (argument === "--url") {
      options.url = nextValue;
      continue;
    }
    if (argument === "--locator") {
      options.locator = nextValue;
      continue;
    }
    if (argument === "--output") {
      options.output = resolveOutputPath(nextValue);
      continue;
    }
    if (argument === "--timeout") {
      options.timeoutMs = parseTimeout(nextValue);
      continue;
    }
    if (argument === "--viewport") {
      options.viewport = parseViewport(nextValue);
      continue;
    }
    if (argument === "--html") {
      options.html = nextValue;
      continue;
    }

    throw new Error(`Unknown option: ${argument}`);
  }

  return { help: false, options };
}

function resolveOutputPath(outputPath) {
  if (path.isAbsolute(outputPath)) {
    return outputPath;
  }

  return path.resolve(docsRoot, outputPath);
}

function parseTimeout(value) {
  const timeoutMs = Number.parseInt(value, 10);
  if (!Number.isInteger(timeoutMs) || timeoutMs <= 0) {
    throw new Error(`Invalid --timeout value: ${value}`);
  }

  return timeoutMs;
}

function parseViewport(value) {
  const match = /^(\d+)x(\d+)$/u.exec(value);
  if (!match) {
    throw new Error(`Invalid --viewport value: ${value}. Expected WIDTHxHEIGHT.`);
  }

  const width = Number.parseInt(match[1], 10);
  const height = Number.parseInt(match[2], 10);
  if (width <= 0 || height <= 0) {
    throw new Error(`Invalid --viewport dimensions: ${value}`);
  }

  return { width, height };
}

async function captureLocatorScreenshot(options) {
  const browser = await chromium.launch();

  try {
    const page = await browser.newPage({ viewport: options.viewport });

    if (options.html) {
      await page.setContent(options.html, { waitUntil: "domcontentloaded" });
    } else {
      await page.goto(options.url, { waitUntil: "networkidle", timeout: options.timeoutMs });
    }

    const target = page.locator(options.locator).first();
    await target.waitFor({ state: "visible", timeout: options.timeoutMs });
    await mkdir(path.dirname(options.output), { recursive: true });
    await target.screenshot({ path: options.output });

    return options.output;
  } finally {
    await browser.close();
  }
}

try {
  const { help, options } = parseArguments(process.argv.slice(2));
  if (help) {
    printHelp();
    process.exit(0);
  }

  const output = await captureLocatorScreenshot(options);
  console.log(`Wrote locator screenshot: ${output}`);
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
}
