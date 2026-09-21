#Requires -Version 7.0
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$ProgressPreference = 'SilentlyContinue'
$projectRoot = $PSScriptRoot
$toolsRoot = Join-Path $projectRoot '.tools/install'
$originalPath = $env:PATH
$locationPushed = $false
$restartRequired = $false

function Get-VerifiedDownload {
    param([string]$Name, [string]$Url, [string]$Sha256)

    $downloadRoot = Join-Path $toolsRoot 'downloads'
    [IO.Directory]::CreateDirectory($downloadRoot) | Out-Null
    $archive = Join-Path $downloadRoot ([IO.Path]::GetFileName($Url))
    if (-not (Test-Path -LiteralPath $archive) -or
        (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $Sha256) {
        Write-Host "Downloading $Name..."
        Invoke-WebRequest -Uri $Url -OutFile "$archive.part"
        if ((Get-FileHash -LiteralPath "$archive.part" -Algorithm SHA256).Hash -ne $Sha256) {
            throw "$Name download failed SHA256 verification: $archive.part"
        }
        Move-Item -LiteralPath "$archive.part" -Destination $archive -Force
    }
    return $archive
}

function Install-PortableArchive {
    param([string]$Name, [string]$Url, [string]$Sha256, [string]$ArchiveRoot, [string]$Destination)

    $archive = Get-VerifiedDownload $Name $Url $Sha256
    $unpackRoot = Join-Path $toolsRoot "unpack/$Name"
    Expand-Archive -LiteralPath $archive -DestinationPath $unpackRoot -Force
    $source = if ($ArchiveRoot) { Join-Path $unpackRoot $ArchiveRoot } else { $unpackRoot }
    [IO.Directory]::CreateDirectory($Destination) | Out-Null
    Get-ChildItem -LiteralPath $source -Force | Copy-Item -Destination $Destination -Recurse -Force
}

function Invoke-InstallCommand {
    param([string]$Executable, [string[]]$Arguments)

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Executable failed with exit code $LASTEXITCODE. Installation stopped; rerun after fixing the error."
    }
}

try {
    if (-not $IsWindows -or [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne 'X64' -or
        [Runtime.InteropServices.RuntimeInformation]::ProcessArchitecture -ne 'X64') {
        throw 'The full installer requires 64-bit Windows and 64-bit PowerShell.'
    }
    Push-Location -LiteralPath $projectRoot
    $locationPushed = $true
    $serverExecutable = Join-Path $projectRoot '.venv/Scripts/dj-sim.exe'
    if (Get-Process -Name 'dj-sim' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $serverExecutable }) {
        throw 'Stop this project server and its Rhythm Lab window before installing, then rerun install.ps1.'
    }
    Write-Host 'Installing the complete project, patched SONARA, frontend and all model assets.'

    $uvCommand = Get-Command uv.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    $uv = if ($uvCommand) { $uvCommand.Source } else { Join-Path $toolsRoot 'uv/uv.exe' }
    if (-not (Test-Path -LiteralPath $uv)) {
        Install-PortableArchive -Name 'uv' -Destination (Join-Path $toolsRoot 'uv') -ArchiveRoot '' `
            -Url 'https://github.com/astral-sh/uv/releases/download/0.11.12/uv-x86_64-pc-windows-msvc.zip' `
            -Sha256 'e46956a6b088a0382101c797eef945c1b03826e629e968d434cf838d42d85b6b'
    }
    Invoke-InstallCommand $uv @('--version')

    $node = Join-Path $toolsRoot 'node/node.exe'
    if (-not (Test-Path -LiteralPath $node)) {
        $nodeCommand = Get-Command node.exe -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
        $node = if ($nodeCommand) { $nodeCommand.Source } else { $node }
    }
    $npm = Join-Path (Split-Path -Parent $node) 'npm.cmd'
    $nodeReady = $false
    if ((Test-Path -LiteralPath $node) -and (Test-Path -LiteralPath $npm)) {
        $nodeVersion = & $node --version
        if ($LASTEXITCODE -eq 0) {
            $parsedNodeVersion = [version]($nodeVersion.TrimStart('v'))
            $nodeReady = ($parsedNodeVersion.Major -eq 20 -and $parsedNodeVersion -ge [version]'20.19.0') -or
                $parsedNodeVersion -ge [version]'22.12.0'
        }
    }
    if (-not $nodeReady) {
        Install-PortableArchive -Name 'node' -Destination (Join-Path $toolsRoot 'node') `
            -ArchiveRoot 'node-v24.15.0-win-x64' `
            -Url 'https://nodejs.org/dist/v24.15.0/node-v24.15.0-win-x64.zip' `
            -Sha256 'cc5149eabd53779ce1e7bdc5401643622d0c7e6800ade18928a767e940bb0e62'
        $node = Join-Path $toolsRoot 'node/node.exe'
        $npm = Join-Path $toolsRoot 'node/npm.cmd'
    }
    $env:PATH = "$(Split-Path -Parent $node);$originalPath"
    Invoke-InstallCommand $node @('--version')

    Write-Host 'Installing all locked Python dependencies...'
    Invoke-InstallCommand $uv @('sync', '--locked')
    $python = Join-Path $projectRoot '.venv/Scripts/python.exe'

    $vcRuntimeCheck = 'import ctypes; [ctypes.CDLL(name) for name in ("vcruntime140.dll", "msvcp140.dll", "vcruntime140_1.dll")]'
    & $python -c $vcRuntimeCheck 2>$null
    if ($LASTEXITCODE -ne 0) {
        $redist = Get-VerifiedDownload -Name 'Microsoft Visual C++ x64 runtime 14.51.36247.0' `
            -Url 'https://download.visualstudio.microsoft.com/download/pr/ebdab8e5-1d7b-4d9f-a11b-cbb1720c3b12/843068991DAAA1F73AD9F6239BCE4D0F6A07A51F18C37EA2A867E9BECA71295C/VC_redist.x64.exe' `
            -Sha256 '843068991DAAA1F73AD9F6239BCE4D0F6A07A51F18C37EA2A867E9BECA71295C'
        $signature = Get-AuthenticodeSignature -LiteralPath $redist
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
            throw 'The Visual C++ runtime installer does not have a valid Microsoft signature.'
        }
        Write-Host 'Installing the Microsoft Visual C++ x64 runtime; Windows may request administrator approval.'
        $redistProcess = Start-Process -FilePath $redist -ArgumentList '/install', '/quiet', '/norestart' `
            -WindowStyle Hidden -Wait -PassThru
        if ($redistProcess.ExitCode -notin @(0, 1638, -2147023258, 3010)) {
            throw "Visual C++ runtime installation failed with exit code $($redistProcess.ExitCode)."
        }
        $restartRequired = $redistProcess.ExitCode -eq 3010
        & $python -c $vcRuntimeCheck 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw 'The Visual C++ x64 runtime is still unavailable. Restart Windows if requested, then rerun install.ps1.'
        }
    }

    # The audio runtime ships in libs/ffmpeg/bin, so nothing is downloaded for it.
    # Use the application's libs/ffmpeg/bin -> DJTS_FFMPEG -> PATH discovery.
    # Preserve its diagnostic if no compatible shared library build is found.
    $ffmpegCheck = @'
import sys
from dj_track_similarity.audio.ffmpeg_runtime import configure_shared_ffmpeg_runtime
try:
    print(f"FFmpeg shared library directory: {configure_shared_ffmpeg_runtime()}")
except RuntimeError as error:
    sys.exit(str(error))
'@
    Invoke-InstallCommand $python @('-c', $ffmpegCheck)

    Write-Host 'Checking the installed audio and ML runtime...'
    $runtimeCheck = @'
from importlib.metadata import version
from dj_track_similarity.audio.ffmpeg_runtime import inspect_audio_runtime
print(inspect_audio_runtime())
import sonara
import sklearn
import torch
import torchaudio
import torchvision
import torchcodec
for package, expected in (("sonara", "0.3.6"), ("torch", "2.11.0+cu130"), ("torchaudio", "2.11.0+cu130"), ("torchvision", "0.26.0+cu130"), ("torchcodec", "0.16.0+cu130")):
    actual = version(package)
    if actual != expected:
        raise RuntimeError(f"{package}: expected {expected}, found {actual}")
    print(f"{package}: {actual}")
if torch.version.cuda != "13.0":
    raise RuntimeError(f"Expected PyTorch CUDA 13.0, found {torch.version.cuda}")
print(f"scikit-learn: {sklearn.__version__}")
print(f"PyTorch CUDA: {torch.version.cuda}; GPU available: {torch.cuda.is_available()}")
if not torch.cuda.is_available():
    print("Packages are installed; GPU analysis needs a compatible NVIDIA GPU and driver.")
'@
    Invoke-InstallCommand $python @('-c', $runtimeCheck)

    Write-Host 'Installing and building the frontend...'
    Invoke-InstallCommand $npm @('--prefix', (Join-Path $projectRoot 'frontend'), 'ci', '--include=dev')
    Invoke-InstallCommand $npm @('--prefix', (Join-Path $projectRoot 'frontend'), 'run', 'build')

    Write-Host 'Installing all pinned model assets (valid existing files are reused)...'
    Invoke-InstallCommand $python @((Join-Path $projectRoot 'scripts/download_models.py'))
    Write-Host 'Installation complete. Start the application with .\run_server.cmd'
    if ($restartRequired) { Write-Host 'Windows requested a restart after installing Visual C++ runtime. Restart before starting the application.' }
}
catch {
    Write-Error $_ -ErrorAction Continue
    exit 1
}
finally {
    $env:PATH = $originalPath
    if ($locationPushed) { Pop-Location }
}
