# Sets up the two harness-specific projections of the shared agent layer.
#
# .workspace/ is the one source of skills, agents, tooling, and working notes.
# Claude Code consumes it as the project-local `dj-track-similarity` plugin;
# this leaves .claude/ for Claude-only configuration, hooks, and runtime state.
# Codex installs the same Claude-compatible source as a local plugin and
# receives generated launcher TOMLs only for the real Markdown agents.
# AgentProof and Superpowers retain their hardcoded root paths through guarded
# junctions whose data lives under .workspace/tools/.

$ErrorActionPreference = 'Stop'

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $workspaceRoot

function Ensure-ToolStateJunction {
    param([Parameter(Mandatory)][string]$Name)

    $statePath = Join-Path $PSScriptRoot $Name
    [System.IO.Directory]::CreateDirectory($statePath) | Out-Null

    $legacyPath = Join-Path $repoRoot ('.' + $Name)
    if (-not (Test-Path -LiteralPath $legacyPath)) {
        New-Item -ItemType Junction -Path $legacyPath -Target $statePath | Out-Null
        Write-Host "created $legacyPath junction -> $statePath"
        return
    }

    $legacyItem = Get-Item -LiteralPath $legacyPath -Force
    if (-not $legacyItem.LinkType) {
        Write-Warning "Keeping existing directory; not replacing it with a junction: $legacyPath"
        return
    }

    $actualTarget = [System.IO.Path]::GetFullPath([string]$legacyItem.Target)
    $expectedTarget = [System.IO.Path]::GetFullPath($statePath)
    if (-not [string]::Equals($actualTarget, $expectedTarget, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to replace an existing link: $legacyPath -> $actualTarget"
    }

    Write-Host "verified $legacyPath junction -> $statePath"
}

$claudeManifest = Join-Path $workspaceRoot '.claude-plugin\plugin.json'
$claudeMarketplace = Join-Path $workspaceRoot '.claude-plugin\marketplace.json'
foreach ($path in @($claudeManifest, $claudeMarketplace)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing Claude Code plugin manifest: $path"
    }
}

foreach ($toolName in @('agentproof', 'superpowers')) {
    Ensure-ToolStateJunction -Name $toolName
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
    & $claude.Source plugin marketplace add $workspaceRoot --scope project
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
    & $codex.Source plugin marketplace add $workspaceRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Codex could not register the project plugin marketplace (exit $LASTEXITCODE)."
    }

    & $codex.Source plugin add 'dj-track-similarity@dj-track-similarity'
    if ($LASTEXITCODE -ne 0) {
        throw "Codex could not install the project plugin (exit $LASTEXITCODE)."
    }
}

& (Join-Path $PSScriptRoot 'sync-codex-agents.ps1')
