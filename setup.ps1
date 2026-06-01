Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoUrl = if ($env:GETSUBTITLE_REPO_URL) { $env:GETSUBTITLE_REPO_URL } else { "https://github.com/fpenguin/getsubtitle.git" }
$AppHome = if ($env:GETSUBTITLE_HOME) { $env:GETSUBTITLE_HOME } else { Join-Path $env:LOCALAPPDATA "getsubtitle" }
$BinDir = if ($env:GETSUBTITLE_BIN_DIR) { $env:GETSUBTITLE_BIN_DIR } else { Join-Path $env:USERPROFILE "bin" }
$AppVenv = Join-Path $AppHome ".venv"

function Say($Message = "") {
    Write-Host $Message
}

function Ask($Prompt, $Default) {
    if (-not [Environment]::UserInteractive) {
        return $Default
    }
    $answer = Read-Host "$Prompt [$Default]"
    if ([string]::IsNullOrWhiteSpace($answer)) {
        return $Default
    }
    return $answer.Trim()
}

function Find-Python {
    if ($env:PYTHON) {
        return $env:PYTHON
    }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return "py -3"
    }
    foreach ($candidate in @("python3.13", "python3.12", "python3.11", "python3.10", "python")) {
        $cmd = Get-Command $candidate -ErrorAction SilentlyContinue
        if ($cmd) {
            return $candidate
        }
    }
    return $null
}

function Invoke-Python {
    param(
        [Parameter(Mandatory = $true)][string]$PythonCmd,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$PythonArgs
    )
    if ($PythonCmd -eq "py -3") {
        & py -3 @PythonArgs
    } else {
        & $PythonCmd @PythonArgs
    }
}

function Test-PythonVersion {
    param([Parameter(Mandatory = $true)][string]$PythonCmd)
    $code = @"
import sys
if sys.version_info < (3, 10):
    print(f"Python 3.10 or newer is required; found {sys.version.split()[0]}.")
    raise SystemExit(1)
print(f"{sys.version_info.major}.{sys.version_info.minor}")
"@
    Invoke-Python $PythonCmd -c $code | Out-Host
}

function Choose-Extras {
    if ($env:GETSUBTITLE_EXTRAS) {
        return $env:GETSUBTITLE_EXTRAS
    }
    Say ""
    Say "Install optional reading-aid backends?"
    Say "  1) All CJK helpers: Japanese furigana + Korean romanization + Mandarin pinyin + Cantonese Jyutping"
    Say "  2) Japanese furigana only"
    Say "  3) Korean romanization only"
    Say "  4) Mandarin pinyin only"
    Say "  5) Cantonese Jyutping only"
    Say "  6) Minimal install"
    $choice = Ask "Choose 1/2/3/4/5/6" "1"
    switch ($choice) {
        "1" { return "furigana,romanization-ko,romanization-zh,romanization-yue" }
        "2" { return "furigana" }
        "3" { return "romanization-ko" }
        "4" { return "romanization-zh" }
        "5" { return "romanization-yue" }
        "6" { return "" }
        default {
            Say "Unknown choice: $choice"
            Say "Using all CJK helpers."
            return "furigana,romanization-ko,romanization-zh,romanization-yue"
        }
    }
}

function Git-InstallSpec {
    param([string]$Extras)
    if ($Extras) {
        return "getsubtitle[$Extras] @ git+$RepoUrl"
    }
    return "getsubtitle @ git+$RepoUrl"
}

function Write-Shim {
    New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
    $cmdPath = Join-Path $BinDir "getsubtitle.cmd"
    $exePath = Join-Path $AppVenv "Scripts\getsubtitle.exe"
    "@echo off`r`n`"$exePath`" %*`r`n" | Set-Content -Encoding ASCII -Path $cmdPath
}

function Run-FirstTimeSetup {
    if ($env:GETSUBTITLE_RUN_SETUP -eq "0") {
        return
    }
    if (-not [Environment]::UserInteractive) {
        Say ""
        Say "Installed. Run this when you are ready:"
        Say "  getsubtitle setup"
        return
    }
    $answer = Ask "Run first-time setup now?" "Y"
    if ($answer -match "^(|y|yes)$") {
        & (Join-Path $AppVenv "Scripts\getsubtitle.exe") setup
    } else {
        Say ""
        Say "Installed. Run this when you are ready:"
        Say "  getsubtitle setup"
    }
}

$PythonCmd = Find-Python
if (-not $PythonCmd) {
    Say "Python 3.10 or newer is required."
    Say "Install it from https://www.python.org/downloads/windows/"
    exit 1
}
Test-PythonVersion $PythonCmd

$Extras = Choose-Extras

if ((Test-Path ".\pyproject.toml") -and (Test-Path ".\getsubtitle_core.py")) {
    Invoke-Python $PythonCmd -m venv ".venv"
    $VenvPython = ".\.venv\Scripts\python.exe"
    & $VenvPython -m pip install --upgrade pip
    if ($Extras) {
        & $VenvPython -m pip install -e ".[$Extras]"
    } else {
        & $VenvPython -m pip install -e .
    }
    Say ""
    Say "Ready. This checkout is installed in editable mode."
    Say "Run:"
    Say "  .\.venv\Scripts\Activate.ps1"
    Say "  getsubtitle setup"
    exit 0
}

New-Item -ItemType Directory -Force -Path $AppHome | Out-Null
Invoke-Python $PythonCmd -m venv $AppVenv
$AppPython = Join-Path $AppVenv "Scripts\python.exe"
& $AppPython -m pip install --upgrade pip
& $AppPython -m pip install (Git-InstallSpec $Extras)
Write-Shim

Say ""
Say "getsubtitle is installed at:"
Say "  $(Join-Path $AppVenv "Scripts\getsubtitle.exe")"
Say ""
Say "Command shim written to:"
Say "  $(Join-Path $BinDir "getsubtitle.cmd")"

$pathParts = [Environment]::GetEnvironmentVariable("Path", "User") -split ";"
if ($pathParts -notcontains $BinDir) {
    Say ""
    Say "Add this folder to your user PATH if 'getsubtitle' is not found:"
    Say "  $BinDir"
}

Run-FirstTimeSetup
