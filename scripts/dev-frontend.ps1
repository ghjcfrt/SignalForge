$ErrorActionPreference = "Stop"

$frontendPort = if ($env:FRONTEND_PORT) { [int]$env:FRONTEND_PORT } else { 5173 }
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\")).Path
$listeners = @(Get-NetTCPConnection -LocalPort $frontendPort -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
    $projectListener = $false
    foreach ($listener in $listeners) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        $commandLine = [string]$process.CommandLine
        if ($commandLine -like "*$workspaceRoot*" -or
            ($commandLine -match '(?i)(vite|vite\.js)' -and
             $commandLine -match '(?i)(^|[\\/ ])frontend([\\/ ]|$)' -and
             $commandLine -match "(?i)(--port\s+)?$frontendPort(\s|$)")) {
            $projectListener = $true
        }
    }

    if ($projectListener) {
        Write-Host "Frontend is already running at http://127.0.0.1:$frontendPort/"
        exit 0
    }

    throw "Port $frontendPort is already in use by another process."
}

Push-Location frontend
try {
    npm run dev -- --host 127.0.0.1 --port $frontendPort
} finally {
    Pop-Location
}
