# Sets up the two harness-specific projections of the shared agent layer.
#
# .djts/ is the one source of skills, agents, plugin scripts, and manifests.
# Claude Code consumes it as the project-local `dj-track-similarity` plugin;
# this leaves .claude/ for Claude-only configuration, hooks, and runtime state.
# Codex installs the same Claude-compatible source as a local plugin and
# receives generated launcher TOMLs only for the real Markdown agents.

$ErrorActionPreference = 'Stop'

$pluginRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $pluginRoot

$claudeManifest = Join-Path $pluginRoot '.claude-plugin\plugin.json'
$claudeMarketplace = Join-Path $pluginRoot '.claude-plugin\marketplace.json'
foreach ($path in @($claudeManifest, $claudeMarketplace)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Claude Code plugin manifest: $path"
    }
}

foreach ($legacyPath in @(
    (Join-Path $repoRoot '.claude\skills'),
    (Join-Path $repoRoot '.claude\agents')
)) {
    if (-not (Test-Path -LiteralPath $legacyPath)) {
        continue
    }

    $item = Get-Item -LiteralPath $legacyPath -Force
    if (-not $item.LinkType) {
        throw "Refusing to replace a real directory: $legacyPath"
    }

    # Never use Remove-Item -Recurse on a reparse point: older PowerShell can
    # follow it and delete the shared source tree.
    [System.IO.Directory]::Delete($legacyPath, $false)
    Write-Host "removed legacy Claude junction: $legacyPath"
}

$claude = Get-Command claude -ErrorAction SilentlyContinue
if ($null -eq $claude) {
    Write-Warning 'Claude Code was not found; skipped the project plugin registration.'
}
else {
    & $claude.Source plugin marketplace add $pluginRoot --scope project
    if ($LASTEXITCODE -ne 0) {
        throw "Claude Code could not register the project plugin marketplace (exit $LASTEXITCODE)."
    }

    & $claude.Source plugin install 'dj-track-similarity@dj-track-similarity' --scope project --yes
    if ($LASTEXITCODE -ne 0) {
        throw "Claude Code could not install the project plugin (exit $LASTEXITCODE)."
    }
}

$codex = Get-Command codex -ErrorAction SilentlyContinue
if ($null -eq $codex) {
    Write-Warning 'Codex CLI was not found; skipped the project plugin registration.'
}
else {
    & $codex.Source plugin marketplace add $pluginRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Codex could not register the project plugin marketplace (exit $LASTEXITCODE)."
    }

    & $codex.Source plugin add 'dj-track-similarity@dj-track-similarity'
    if ($LASTEXITCODE -ne 0) {
        throw "Codex could not install the project plugin (exit $LASTEXITCODE)."
    }
}

& (Join-Path $PSScriptRoot 'sync-codex-agents.ps1')
