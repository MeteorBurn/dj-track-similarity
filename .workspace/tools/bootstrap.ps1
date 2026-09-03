# Restores the links that let Claude Code reach the shared agent layer.
#
# .workspace/ holds one copy of everything: skills (methods), agents (the workers
# that carry them) and working notes. A skill that should run in isolation says
# so itself, with `context: fork` in its own frontmatter.
#
# Codex finds .workspace/skills on its own — it is a documented project skill root,
# scanned from the working directory up to the repository root, and it ignores
# the Claude-only frontmatter keys. It cannot read Markdown agents at all, so
# sync-codex-agents.ps1 projects those into .codex/agents/*.toml. Claude Code
# scans only .claude/skills and .claude/agents, so those two paths are junctions
# into .workspace/. Junctions are not stored by git, so a fresh clone needs this
# script once.
#
# Junctions are used rather than symbolic links because they need neither
# administrator rights nor Developer Mode. Both harnesses follow either kind;
# this was verified against live sessions of both.

$ErrorActionPreference = 'Stop'

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $workspaceRoot

$links = @(
    # Claude Code scans these two and nothing else.
    @{ Link = Join-Path $repoRoot '.claude\skills'; Target = Join-Path $workspaceRoot 'skills' }
    @{ Link = Join-Path $repoRoot '.claude\agents'; Target = Join-Path $workspaceRoot 'agents' }
    # Codex scans .agents/skills from the working directory up to the repository
    # root. The name is its convention, not ours, so the path stays and holds
    # nothing but this link.
    @{ Link = Join-Path $repoRoot '.agents\skills'; Target = Join-Path $workspaceRoot 'skills' }
)

foreach ($entry in $links) {
    $link = $entry.Link
    $target = $entry.Target
    if (-not (Test-Path -LiteralPath $target)) {
        throw "Missing target, refusing to link: $target"
    }

    if (Test-Path -LiteralPath $link) {
        $item = Get-Item -LiteralPath $link -Force
        if ($item.LinkType) {
            # Never use Remove-Item -Recurse on a reparse point: older PowerShell
            # follows it and deletes the target, which here is the canon itself.
            [System.IO.Directory]::Delete($link, $false)
        }
        else {
            throw "Refusing to replace a real directory: $link"
        }
    }

    [System.IO.Directory]::CreateDirectory((Split-Path -Parent $link)) | Out-Null
    New-Item -ItemType Junction -Path $link -Target $target | Out-Null
    Write-Host "linked $link -> $target"
}

& (Join-Path $PSScriptRoot 'sync-codex-agents.ps1')
