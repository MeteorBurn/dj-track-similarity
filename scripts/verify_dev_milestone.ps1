#Requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$Smoke,
    [switch]$SkipBackend,
    [switch]$SkipFrontend,
    [switch]$SkipDocs,
    [switch]$SkipBenchmark,
    [string]$Python,
    [switch]$IncludeMl,
    [string]$MlPython,
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

function Resolve-ExecutableCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string]$Description
    )

    if ([string]::IsNullOrWhiteSpace($Command)) {
        throw "$Description was not specified."
    }

    if (Test-Path -LiteralPath $Command -PathType Leaf) {
        return (Resolve-Path -LiteralPath $Command).Path
    }

    $resolvedCommand = Get-Command $Command -ErrorAction SilentlyContinue
    if ($null -eq $resolvedCommand) {
        throw "$Description was not found: $Command"
    }

    return $resolvedCommand.Source
}

function Get-MlPythonCommand {
    param([string]$RequestedPython)

    if (-not [string]::IsNullOrWhiteSpace($RequestedPython)) {
        return Resolve-ExecutableCommand -Command $RequestedPython -Description "ML Python"
    }

    if (-not [string]::IsNullOrWhiteSpace($env:DJ_TRACK_SIMILARITY_ML_PYTHON)) {
        return Resolve-ExecutableCommand -Command $env:DJ_TRACK_SIMILARITY_ML_PYTHON -Description "ML Python from DJ_TRACK_SIMILARITY_ML_PYTHON"
    }

    throw "ML verification requires -MlPython or DJ_TRACK_SIMILARITY_ML_PYTHON. Point it at the prepared Python executable without reinstalling or repointing that environment."
}

function Invoke-WithRepoSourcePythonPath {
    param([Parameter(Mandatory = $true)][scriptblock]$ScriptBlock)

    $repoSourcePath = Join-Path $RepoRoot "src"
    if (-not (Test-Path -LiteralPath $repoSourcePath -PathType Container)) {
        throw "Missing repository source directory for ML verification: $repoSourcePath"
    }

    $originalPythonPath = $env:PYTHONPATH
    $originalDontWriteBytecode = $env:PYTHONDONTWRITEBYTECODE
    if ([string]::IsNullOrWhiteSpace($originalPythonPath)) {
        $env:PYTHONPATH = $repoSourcePath
    }
    else {
        $pathSeparator = [System.IO.Path]::PathSeparator
        $env:PYTHONPATH = "$repoSourcePath$pathSeparator$originalPythonPath"
    }
    $env:PYTHONDONTWRITEBYTECODE = "1"

    try {
        & $ScriptBlock
    }
    finally {
        if ($null -eq $originalPythonPath) {
            Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue
        }
        else {
            $env:PYTHONPATH = $originalPythonPath
        }

        if ($null -eq $originalDontWriteBytecode) {
            Remove-Item Env:\PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
        }
        else {
            $env:PYTHONDONTWRITEBYTECODE = $originalDontWriteBytecode
        }
    }
}

function Get-MlPreflightPythonCode {
    return @'
import importlib
import pathlib
import sys


def is_relative_to(path: pathlib.Path, parent: pathlib.Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


repo_root = pathlib.Path(sys.argv[1]).resolve()
repo_src = (repo_root / "src").resolve()

for module_name in ("torch", "torchaudio", "torchvision", "torchcodec"):
    importlib.import_module(module_name)

import torch

if not torch.cuda.is_available():
    raise SystemExit("torch.cuda.is_available() returned false")

cuda_probe = torch.tensor([1.0, 2.0], device="cuda")
cuda_result = float((cuda_probe * 2.0).sum().item())
if cuda_result != 6.0:
    raise SystemExit(f"CUDA tensor operation returned unexpected result: {cuda_result}")

import dj_track_similarity

package_file = pathlib.Path(dj_track_similarity.__file__).resolve()
if not is_relative_to(package_file, repo_src):
    raise SystemExit(
        "dj_track_similarity imported from outside the dev repository source tree: "
        f"{package_file}"
    )

print(f"ML preflight OK: dj_track_similarity import path: {package_file}")
print(
    "ML preflight OK: "
    f"torch={torch.__version__}; cuda={torch.version.cuda}; device={torch.cuda.get_device_name(0)}"
)
'@
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
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [string[]]$DisplayArguments
    )

    if (-not (Test-Path -LiteralPath $WorkingDirectory -PathType Container)) {
        throw "Missing working directory for ${Name}: $WorkingDirectory"
    }

    Write-Host ""
    Write-Host "==> $Name"
    $previewArguments = $Arguments
    if ($PSBoundParameters.ContainsKey("DisplayArguments")) {
        $previewArguments = $DisplayArguments
    }
    Write-Host ("    {0} {1}" -f $FilePath, ($previewArguments -join " "))

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

function Invoke-MlVerification {
    param([Parameter(Mandatory = $true)][string]$PythonCommand)

    Invoke-WithRepoSourcePythonPath {
        $preflightScriptPath = Join-Path ([System.IO.Path]::GetTempPath()) "dj-track-similarity-ml-preflight-$([System.Guid]::NewGuid()).py"
        try {
            Set-Content -LiteralPath $preflightScriptPath -Value (Get-MlPreflightPythonCode) -Encoding UTF8
            Invoke-VerificationStep `
                -Name "ML/CUDA preflight" `
                -FilePath $PythonCommand `
                -Arguments @($preflightScriptPath, $RepoRoot) `
                -DisplayArguments @("<temp ml/cuda preflight>", $RepoRoot) `
                -WorkingDirectory $RepoRoot
        }
        finally {
            if (Test-Path -LiteralPath $preflightScriptPath -PathType Leaf) {
                Remove-Item -LiteralPath $preflightScriptPath -Force
            }
        }

        Invoke-VerificationStep `
            -Name "Backend ML pytest suite" `
            -FilePath $PythonCommand `
            -Arguments @("-m", "pytest", "-m", "ml", "-q") `
            -WorkingDirectory $RepoRoot
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
$mlPythonCommand = $null
if ($IncludeMl) {
    $mlPythonCommand = Get-MlPythonCommand $MlPython
}
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

if ($IncludeMl -and -not $SkipBackend) {
    Invoke-MlVerification -PythonCommand $mlPythonCommand
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
