param(
    [int]$Port = 8787,
    [string]$TaskName = "Interday Trading Dashboard",
    [switch]$OpenBrowser
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$StartScript = Join-Path $RepoRoot "scripts\Start-InterdayWeb.ps1"

if (-not (Test-Path $StartScript)) {
    throw "Start script not found: $StartScript"
}

$argumentParts = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$StartScript`"",
    "-Port", $Port
)
if ($OpenBrowser) {
    $argumentParts += "-OpenBrowser"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument ($argumentParts -join " ") `
    -WorkingDirectory $RepoRoot

$trigger = New-ScheduledTaskTrigger -AtLogOn
$trigger.Delay = "PT30S"

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

$installedVia = "Task Scheduler"
try {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description "Auto-start local IDX Interday Trading Dashboard at user logon." | Out-Null
} catch {
    $startupDir = [Environment]::GetFolderPath("Startup")
    if (-not $startupDir) {
        throw
    }

    $startupCmd = Join-Path $startupDir "Interday Trading Dashboard.cmd"
    $openBrowserArg = if ($OpenBrowser) { " -OpenBrowser" } else { "" }
    $cmdContent = @"
@echo off
cd /d "$RepoRoot"
start "Interday Trading Dashboard" /min powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$StartScript" -Port $Port$openBrowserArg
"@
    Set-Content -Path $startupCmd -Value $cmdContent -Encoding ASCII
    $installedVia = "Startup folder fallback ($startupCmd)"
}

Write-Host "Installed auto-start via: $installedVia"
Write-Host "Dashboard URL: http://127.0.0.1:$Port/"
Write-Host "Manual start: powershell -ExecutionPolicy Bypass -File `"$StartScript`" -Port $Port"
