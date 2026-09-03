# Projects the shared agent layer into the shape Codex needs.
#
# Two inputs, one output directory:
#
#   .workspace/agents/<name>.md          a real agent: a worker with a role and a
#                                     tool surface. Claude reads it directly
#                                     through the .claude/agents junction.
#   .workspace/skills/<name>/SKILL.md    a method. Only those marked `context: fork`
#     with `context: fork`            are projected: Claude forks them by itself,
#                                     Codex has no per-skill fork flag and needs a
#                                     callable file.
#
# Everything lands in .codex/agents/*.toml. Those files are disposable — edit the
# Markdown, never the TOML.
#
# What crosses the two formats, and what does not:
#
#   name, description, body  ->  name, description, developer_instructions
#   tools without write      ->  sandbox_mode = "read-only"
#   effort                   ->  model_reasoning_effort
#   model                    ->  NOT ported. Claude takes `inherit`/`sonnet`,
#                                Codex takes gpt-5.6*; translating would lie.
#   skills                   ->  named in the preamble, not emitted as
#                                [[skills.config]]. That key is a per-skill
#                                enablement override, and every skill under
#                                .workspace/skills is already discoverable by Codex,
#                                so an override would add nothing and its path
#                                base is not documented clearly enough to risk.
#
# The body is copied verbatim. No harness name is ever substituted: a blanket
# search-and-replace over the body is what produced "so Codex and Codex run the
# same instructions" in an earlier generation. Keep bodies harness-neutral.
#
# The body is emitted as a TOML *literal* multiline string. A basic one
# ("""...""") treats a backslash as an escape, and these bodies carry Windows
# paths, which makes the whole document unparsable.

$ErrorActionPreference = 'Stop'

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$repoRoot = Split-Path -Parent $workspaceRoot
$agentsDir = Join-Path $workspaceRoot 'agents'
$skillsDir = Join-Path $workspaceRoot 'skills'
$targetDir = Join-Path $repoRoot '.codex\agents'
[System.IO.Directory]::CreateDirectory($targetDir) | Out-Null

$frontmatterPattern = '(?s)^---\r?\n(.*?)\r?\n---\r?\n(.*)$'
$namePattern = '(?m)^name:[ \t]*(.+?)[ \t\r]*$'
$descriptionPattern = '(?m)^description:[ \t]*(.+?)[ \t\r]*$'
$toolsPattern = '(?m)^tools:[ \t]*(.+?)[ \t\r]*$'
$effortPattern = '(?m)^effort:[ \t]*(.+?)[ \t\r]*$'
$sandboxPattern = '(?m)^sandbox_mode:[ \t]*(.+?)[ \t\r]*$'
$forkPattern = '(?m)^context:[ \t]*fork[ \t\r]*$'
$skillsBlockPattern = '(?ms)^skills:[ \t\r]*\n((?:[ \t]*-[ \t]*\S.*\r?\n?)+)'

$writeTools = @('Write', 'Edit', 'Bash', 'PowerShell', 'NotebookEdit')

function Split-Frontmatter([string]$path, [string]$label) {
    $text = Get-Content -LiteralPath $path -Raw
    if ($text -notmatch $frontmatterPattern) { throw "No YAML frontmatter: $label" }
    return @{ Frontmatter = $Matches[1]; Body = $Matches[2].Trim() }
}

function Write-CodexAgent {
    param(
        [string]$Name,
        [string]$Description,
        [string]$Body,
        [string]$SandboxMode,
        [string]$Effort,
        [string[]]$Skills,
        [string]$Origin
    )
    if ($Body -match "'''") { throw "body contains a TOML literal-string delimiter: $Name" }

    # Only add the pointer to AGENTS.md when the body does not already carry
    # one. A self-contained agent that states its own project contract does not
    # need it said twice.
    $preambleLines = @()
    if ($Body -notmatch 'AGENTS\.md') {
        $preambleLines += 'Follow the instructions below. `AGENTS.md` at the repository root governs this project and outranks any habit of your own; read it as well.'
    }
    if ($Skills.Count -gt 0) {
        $preambleLines += ''
        $preambleLines += "Skills that belong to this role, under .workspace/skills/: $($Skills -join ', '). Read the ones the task needs."
    }

    $escaped = $Description.Replace('\', '\\').Replace('"', '\"')
    $lines = @(
        "# Generated from $Origin by .workspace/tools/sync-codex-agents.ps1."
        '# Do not edit: rerun the script instead.'
        "name = `"$Name`""
        "description = `"$escaped`""
    )
    if ($SandboxMode) { $lines += "sandbox_mode = `"$SandboxMode`"" }
    if ($Effort) { $lines += "model_reasoning_effort = `"$Effort`"" }
    $lines += "developer_instructions = '''"
    $lines += $preambleLines
    $lines += ''
    $lines += $Body
    $lines += "'''"

    Set-Content -LiteralPath (Join-Path $targetDir "$Name.toml") -Value ($lines -join "`n") -Encoding utf8
}

$written = @()

# --- real agents -----------------------------------------------------------
if (Test-Path -LiteralPath $agentsDir) {
    foreach ($file in Get-ChildItem -LiteralPath $agentsDir -Filter '*.md' | Sort-Object Name) {
        $parts = Split-Frontmatter $file.FullName $file.Name
        $fm = $parts.Frontmatter

        $name = [regex]::Match($fm, $namePattern).Groups[1].Value.Trim()
        $description = [regex]::Match($fm, $descriptionPattern).Groups[1].Value.Trim()
        if (-not $name) { throw "name missing: $($file.Name)" }
        if (-not $description) { throw "description missing: $($file.Name)" }

        # Codex has no equivalent of the `tools` allowlist; the closest honest
        # projection is the sandbox. An explicit `sandbox_mode:` in the
        # frontmatter wins — Claude ignores the key, so it is a clean way to
        # state an intent the tool list cannot express, such as an agent that
        # may run commands but must not write. Otherwise infer: a surface with
        # no file-writing tool is a read-only worker.
        $sandbox = [regex]::Match($fm, $sandboxPattern).Groups[1].Value.Trim()
        if (-not $sandbox) {
            $toolsRaw = [regex]::Match($fm, $toolsPattern).Groups[1].Value
            if ($toolsRaw) {
                $tools = $toolsRaw.Split(',') | ForEach-Object { $_.Trim() }
                $canWrite = $false
                foreach ($t in $tools) { if ($writeTools -contains $t) { $canWrite = $true } }
                $sandbox = if ($canWrite) { 'workspace-write' } else { 'read-only' }
            }
        }

        $effort = [regex]::Match($fm, $effortPattern).Groups[1].Value.Trim()
        if ($effort -eq 'max') { $effort = 'xhigh' }

        $skills = @()
        $skillsBlock = [regex]::Match($fm, $skillsBlockPattern).Groups[1].Value
        if ($skillsBlock) {
            $skills = $skillsBlock -split "`n" | ForEach-Object { ($_ -replace '^[ \t]*-[ \t]*', '').Trim() } | Where-Object { $_ }
        }

        Write-CodexAgent -Name $name -Description $description -Body $parts.Body `
            -SandboxMode $sandbox -Effort $effort -Skills $skills `
            -Origin ".workspace/agents/$($file.Name)"
        $written += $name
    }
}

# --- forkable skills -------------------------------------------------------
foreach ($skill in Get-ChildItem -LiteralPath $skillsDir -Directory | Sort-Object Name) {
    $skillFile = Join-Path $skill.FullName 'SKILL.md'
    if (-not (Test-Path -LiteralPath $skillFile)) { continue }

    $parts = Split-Frontmatter $skillFile $skill.Name
    if ($parts.Frontmatter -notmatch $forkPattern) { continue }

    $name = [regex]::Match($parts.Frontmatter, $namePattern).Groups[1].Value.Trim()
    $description = [regex]::Match($parts.Frontmatter, $descriptionPattern).Groups[1].Value.Trim()
    if (-not $name) { throw "name missing: $($skill.Name)" }
    if (-not $description) { throw "description missing: $($skill.Name)" }
    if ($written -contains $name) { throw "name collides with an agent: $name" }

    Write-CodexAgent -Name $name -Description $description -Body $parts.Body `
        -SandboxMode '' -Effort '' -Skills @() `
        -Origin ".workspace/skills/$name/SKILL.md"
    $written += $name
}

# --- drop what no longer has a source --------------------------------------
foreach ($existing in Get-ChildItem -LiteralPath $targetDir -Filter '*.toml') {
    if ($written -notcontains $existing.BaseName) {
        [System.IO.File]::Delete($existing.FullName)
        Write-Host "dropped orphan: $($existing.Name)"
    }
}

Write-Host "generated $($written.Count): $($written -join ', ')"
