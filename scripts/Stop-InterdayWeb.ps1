param(
    [int]$Port = 8787
)

$ErrorActionPreference = "Stop"

$connections = Get-NetTCPConnection -LocalAddress "127.0.0.1" -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $connections) {
    Write-Host "No Interday web listener found on http://127.0.0.1:$Port/"
    exit 0
}

$processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique
foreach ($processId in $processIds) {
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        Write-Host "Stopping process $processId ($($process.ProcessName)) listening on port $Port..."
        Stop-Process -Id $processId -Force
    }
}

Write-Host "Stopped Interday web on port $Port."
