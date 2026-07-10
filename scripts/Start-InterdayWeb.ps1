param(
    [int]$Port = 8787,
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

$LogDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "interday-web.log"

function Write-StartupLog {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    try {
        "[$timestamp] $Message" | Add-Content -Path $LogFile -Encoding UTF8
    } catch {
        Write-Host "[$timestamp] $Message"
    }
}

function Test-CommandAvailable {
    param([string]$Command)
    return [bool](Get-Command $Command -ErrorAction SilentlyContinue)
}

function Test-PythonUsable {
    param([string]$Command)
    try {
        & $Command --version *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        Write-StartupLog "Skipping Python candidate '$Command': $($_.Exception.Message)"
        return $false
    }
}

function Resolve-PythonCommand {
    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        if (Test-PythonUsable $venvPython) {
            return $venvPython
        }
    }

    foreach ($candidate in @("py", "python")) {
        if (Test-CommandAvailable $candidate) {
            if (Test-PythonUsable $candidate) {
                return $candidate
            }
        }
    }

    $localPythonCandidates = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python310\python.exe")
    )
    foreach ($candidate in $localPythonCandidates) {
        if ((Test-Path $candidate) -and (Test-PythonUsable $candidate)) {
            return $candidate
        }
    }

    throw "Python executable not found. Install Python or repair .venv, then rerun this script."
}

$listener = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    Write-StartupLog "Interday web appears to already be listening on http://127.0.0.1:$Port/"
    if ($OpenBrowser) {
        Start-Process "http://127.0.0.1:$Port/"
    }
    exit 0
}

$python = Resolve-PythonCommand
$srcPath = Join-Path $RepoRoot "src"
if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$srcPath;$env:PYTHONPATH"
} else {
    $env:PYTHONPATH = $srcPath
}

Write-StartupLog "Starting Interday web from $RepoRoot on http://127.0.0.1:$Port/ using '$python'"
if ($OpenBrowser) {
    Start-Process "http://127.0.0.1:$Port/"
}

$ErrorActionPreference = "Continue"
& $python -m uvicorn interday_liquidity_screener.server:app --host 127.0.0.1 --port $Port --log-level info >> $LogFile 2>&1
