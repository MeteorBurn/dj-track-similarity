import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import test from "node:test";
import ts from "typescript";

// Every frontend test must run the module it checks, not read it as text.
// Source-text assertions pin how a component is written instead of what it
// does: they break on harmless renames and stay green when behaviour breaks.
//
// A test counts as executing when its callback reaches, directly or through
// file-level helpers and variables, one of:
//   - `server.ssrLoadModule(...)` for React components
//   - `ts.transpileModule(...)` for plain modules run with `vm` or imported
//   - a binding imported from `../src/`, or `import("../src/...")`
// Reaching one is required, not sufficient: review still judges the assertions.

const LOADER_CALLS = new Set(["ssrLoadModule", "transpileModule"]);

function testFileNames() {
  return readdirSync(new URL(".", import.meta.url))
    .filter((name) => name.endsWith(".test.mjs") && name !== "testsExecuteCode.test.mjs")
    .sort();
}

function isSourcePath(node) {
  return node !== undefined && ts.isStringLiteralLike(node) && node.text.startsWith("../src/");
}

function isLoaderCall(node) {
  if (!ts.isCallExpression(node)) return false;
  if (node.expression.kind === ts.SyntaxKind.ImportKeyword) return isSourcePath(node.arguments[0]);
  const callee = ts.isPropertyAccessExpression(node.expression) ? node.expression.name : node.expression;
  return ts.isIdentifier(callee) && LOADER_CALLS.has(callee.text);
}

function isPropertyName(node) {
  const parent = node.parent;
  return (ts.isPropertyAccessExpression(parent) && parent.name === node)
    || (ts.isPropertyAssignment(parent) && parent.name === node);
}

function boundNames(name) {
  if (ts.isIdentifier(name)) return [name.text];
  return name.elements.flatMap((element) => (ts.isOmittedExpression(element) ? [] : boundNames(element.name)));
}

function nonExecutingTests(fileName, source) {
  const file = ts.createSourceFile(fileName, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.JS);
  const executing = new Set();
  const definitions = new Map();
  const tests = [];
  const define = (name, node) => definitions.set(name, [...(definitions.get(name) ?? []), node]);

  const collect = (node) => {
    if (ts.isImportDeclaration(node) && isSourcePath(node.moduleSpecifier)) {
      const clause = node.importClause;
      if (clause?.name) executing.add(clause.name.text);
      const bindings = clause?.namedBindings;
      if (bindings && ts.isNamespaceImport(bindings)) executing.add(bindings.name.text);
      if (bindings && ts.isNamedImports(bindings)) {
        for (const element of bindings.elements) executing.add(element.name.text);
      }
    } else if (ts.isFunctionDeclaration(node) && node.name && node.body) {
      define(node.name.text, node.body);
    } else if (ts.isVariableDeclaration(node) && node.initializer) {
      for (const name of boundNames(node.name)) define(name, node.initializer);
    } else if (
      ts.isBinaryExpression(node)
      && node.operatorToken.kind === ts.SyntaxKind.EqualsToken
      && ts.isIdentifier(node.left)
    ) {
      define(node.left.text, node.right);
    } else if (ts.isCallExpression(node) && ts.isIdentifier(node.expression) && node.expression.text === "test") {
      tests.push({ title: node.arguments[0]?.getText(file) ?? "<untitled>", body: node.arguments.at(-1) });
    }
    ts.forEachChild(node, collect);
  };
  collect(file);

  const reaches = (node) => isLoaderCall(node)
    || (ts.isIdentifier(node) && executing.has(node.text) && !isPropertyName(node))
    || ts.forEachChild(node, reaches) === true;

  // A helper or variable executes once anything it is defined from does.
  for (let grew = true; grew;) {
    grew = false;
    for (const [name, nodes] of definitions) {
      if (!executing.has(name) && nodes.some(reaches)) {
        executing.add(name);
        grew = true;
      }
    }
  }

  return tests.filter(({ body }) => body === undefined || !reaches(body)).map(({ title }) => title);
}

test("every frontend test executes the module it checks", () => {
  const offenders = testFileNames().flatMap((name) =>
    nonExecutingTests(name, readFileSync(new URL(name, import.meta.url), "utf8"))
      .map((title) => `${name}: ${title}`)
  );

  assert.deepEqual(
    offenders,
    [],
    `These tests never reach the module under test. Load it with ssrLoadModule, `
      + `transpileModule, or a ../src/ import in the test or a helper it calls:\n`
      + offenders.map((offender) => `  - ${offender}`).join("\n")
  );
});
