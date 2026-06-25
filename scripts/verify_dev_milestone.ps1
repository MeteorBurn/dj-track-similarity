#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$Smoke,
    [switch]$SkipBackend,
    [switch]$SkipFrontend,
    [switch]$SkipDocs,
    [switch]$SkipBenchmark,
    [string]$Python,
    [string]$BenchmarkOutput
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$PyprojectPath = Join-Path $RepoRoot "pyproject.toml"

if (-not (Test-Path -LiteralPath $PyprojectPath -PathType Leaf)) {
    throw "verify_dev_milestone.ps1 must be run from the dj-track-similarity repository layout. Missing: $PyprojectPath"
}

function Get-PythonCommand {
    param([string]$RequestedPython)

    if (-not [string]::IsNullOrWhiteSpace($RequestedPython)) {
        return $RequestedPython
    }

    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        return $venvPython
    }

    return "python"
}

function Get-NpmCommand {
    $npmCommand = Get-Command "npm.cmd" -ErrorAction SilentlyContinue
    if ($null -ne $npmCommand) {
        return $npmCommand.Source
    }

    $npmCommand = Get-Command "npm" -ErrorAction SilentlyContinue
    if ($null -eq $npmCommand) {
        throw "npm was not found on PATH. Install frontend/docs dependencies before running the milestone gate."
    }

    return $npmCommand.Source
}

function ConvertTo-RepoRelativePath {
    param([string]$Path)

    $fullPath = (Resolve-Path -LiteralPath $Path).Path
    if (-not $fullPath.StartsWith($RepoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $fullPath
    }

    return $fullPath.Substring($RepoRoot.Length).TrimStart("\", "/")
}

function Get-FocusedRegressionTargets {
    $testsRoot = Join-Path $RepoRoot "tests"
    if (-not (Test-Path -LiteralPath $testsRoot -PathType Container)) {
        throw "Missing tests directory: $testsRoot"
    }

    $targets = New-Object System.Collections.Generic.List[string]
    $evaluationDirectory = Join-Path $testsRoot "evaluation"
    if (Test-Path -LiteralPath $evaluationDirectory -PathType Container) {
        $targets.Add((ConvertTo-RepoRelativePath $evaluationDirectory))
    }

    Get-ChildItem -LiteralPath $testsRoot -Filter "test_evaluation*.py" -File |
        Sort-Object -Property Name |
        ForEach-Object { $targets.Add((ConvertTo-RepoRelativePath $_.FullName)) }

    $apiEvaluationTest = Join-Path $testsRoot "test_api_evaluation.py"
    if (Test-Path -LiteralPath $apiEvaluationTest -PathType Leaf) {
        $targets.Add((ConvertTo-RepoRelativePath $apiEvaluationTest))
    }

    Get-ChildItem -LiteralPath $testsRoot -Filter "test_*search*.py" -File |
        Sort-Object -Property Name |
        ForEach-Object { $targets.Add((ConvertTo-RepoRelativePath $_.FullName)) }

    $seenTargets = @{}
    $uniqueTargets = @()
    foreach ($target in $targets) {
        $key = $target.ToLowerInvariant()
        if ($seenTargets.ContainsKey($key)) {
            continue
        }
        $seenTargets[$key] = $true
        $uniqueTargets += $target
    }

    if ($uniqueTargets.Count -eq 0) {
        throw "No evaluation or search pytest targets were found under: $testsRoot"
    }

    return $uniqueTargets
}

function Invoke-VerificationStep {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory
    )

    if (-not (Test-Path -LiteralPath $WorkingDirectory -PathType Container)) {
        throw "Missing working directory for ${Name}: $WorkingDirectory"
    }

    Write-Host ""
    Write-Host "==> $Name"
    Write-Host ("    {0} {1}" -f $FilePath, ($Arguments -join " "))

    Push-Location -LiteralPath $WorkingDirectory
    try {
        & $FilePath @Arguments
        $exitCode = $LASTEXITCODE
        if ($null -eq $exitCode) {
            $exitCode = 0
        }
        if ($exitCode -ne 0) {
            throw "$Name failed with exit code $exitCode"
        }
    }
    finally {
        Pop-Location
    }
}

function Get-BenchmarkOutputPath {
    param([string]$RequestedOutput)

    if (-not [string]::IsNullOrWhiteSpace($RequestedOutput)) {
        return [System.IO.Path]::GetFullPath($RequestedOutput)
    }

    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    return Join-Path ([System.IO.Path]::GetTempPath()) "dj-track-similarity-benchmark-$timestamp.json"
}

$pythonCommand = Get-PythonCommand $Python
$npmCommand = Get-NpmCommand
$focusedRegressionTargets = Get-FocusedRegressionTargets

if (-not $SkipBackend) {
    if ($Smoke) {
        Invoke-VerificationStep `
            -Name "Backend focused non-ML regression tests" `
            -FilePath $pythonCommand `
            -Arguments (@("-m", "pytest", "-m", "not ml") + $focusedRegressionTargets + @("-q")) `
            -WorkingDirectory $RepoRoot
    }
    else {
        Invoke-VerificationStep `
            -Name "Backend full non-ML pytest suite" `
            -FilePath $pythonCommand `
            -Arguments @("-m", "pytest", "-m", "not ml") `
            -WorkingDirectory $RepoRoot

        Invoke-VerificationStep `
            -Name "Backend evaluation and search regression tests" `
            -FilePath $pythonCommand `
            -Arguments (@("-m", "pytest", "-m", "not ml") + $focusedRegressionTargets + @("-q")) `
            -WorkingDirectory $RepoRoot
    }
}

if (-not $SkipFrontend) {
    $frontendRoot = Join-Path $RepoRoot "frontend"
    Invoke-VerificationStep -Name "Frontend typecheck" -FilePath $npmCommand -Arguments @("run", "typecheck") -WorkingDirectory $frontendRoot
    Invoke-VerificationStep -Name "Frontend tests" -FilePath $npmCommand -Arguments @("run", "test") -WorkingDirectory $frontendRoot
    Invoke-VerificationStep -Name "Frontend build" -FilePath $npmCommand -Arguments @("run", "build") -WorkingDirectory $frontendRoot
}

if (-not $SkipDocs) {
    $docsRoot = Join-Path $RepoRoot "docs\dj-track-similarity"
    Invoke-VerificationStep -Name "Documentation build" -FilePath $npmCommand -Arguments @("run", "build") -WorkingDirectory $docsRoot
}

if (-not $SkipBenchmark) {
    $benchmarkOutputPath = Get-BenchmarkOutputPath $BenchmarkOutput
    $benchmarkTrackCount = 1000
    $benchmarkEmbeddingDim = 128
    $benchmarkSeedCount = 20
    $benchmarkPerSource = 30
    if ($Smoke) {
        $benchmarkTrackCount = 25
        $benchmarkEmbeddingDim = 8
        $benchmarkSeedCount = 3
        $benchmarkPerSource = 5
    }

    Invoke-VerificationStep `
        -Name "Search benchmark smoke" `
        -FilePath $pythonCommand `
        -Arguments @(
            "scripts\benchmark_search.py",
            "--output", $benchmarkOutputPath,
            "--track-count", "$benchmarkTrackCount",
            "--embedding-dim", "$benchmarkEmbeddingDim",
            "--seed-count", "$benchmarkSeedCount",
            "--per-source", "$benchmarkPerSource",
            "--vector-backend", "exact"
        ) `
        -WorkingDirectory $RepoRoot

    Write-Host "Benchmark report written outside the repository: $benchmarkOutputPath"
}

Write-Host ""
Write-Host "dev milestone verification completed successfully."
