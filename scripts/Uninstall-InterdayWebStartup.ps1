param(
    [string]$TaskName = "Interday Trading Dashboard"
)

$ErrorActionPreference = "Stop"

$existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed startup task: $TaskName"
}

$startupDir = [Environment]::GetFolderPath("Startup")
if ($startupDir) {
    $startupCmd = Join-Path $startupDir "Interday Trading Dashboard.cmd"
    if (Test-Path $startupCmd) {
        Remove-Item -LiteralPath $startupCmd -Force
        Write-Host "Removed startup launcher: $startupCmd"
    }
}

if (-not $existing) {
    Write-Host "Scheduled task not found: $TaskName"
}
