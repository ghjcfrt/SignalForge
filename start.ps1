$ErrorActionPreference = "Stop"

$workspaceRoot = (Resolve-Path $PSScriptRoot).Path
$backendPort = if ($env:BACKEND_PORT) { [int]$env:BACKEND_PORT } else { 8017 }
$frontendPort = if ($env:FRONTEND_PORT) { [int]$env:FRONTEND_PORT } else { 5173 }

function Get-UvCommand {
    if (Get-Command uv -ErrorAction SilentlyContinue) { return "uv" }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        try { python -m uv --version | Out-Null; return "python -m uv" } catch {}
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try { py -m uv --version | Out-Null; return "py -m uv" } catch {}
    }
    throw "uv not found. Please run .\scripts\setup.ps1 first."
}

function Test-ProjectListener([int]$port) {
    $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if ($process -and [string]$process.CommandLine -like "*$workspaceRoot*") { return $true }
    }
    return $false
}


foreach ($port in @($backendPort, $frontendPort)) {
    if ((Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) -and -not (Test-ProjectListener $port)) {
        throw "Port $port is already in use by another process."
    }
}

$uv = Get-UvCommand
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue) -or -not (Get-Command node.exe -ErrorAction SilentlyContinue)) {
    throw "Node.js/npm not found. Install Node.js and ensure its installation directory is in PATH, then reopen PowerShell."
}
if (-not (Test-ProjectListener $backendPort)) {
    $backendCommand = "$uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port $backendPort"
    Start-Process powershell -WorkingDirectory $workspaceRoot -ArgumentList @("-NoExit", "-Command", $backendCommand) | Out-Null
}
if (-not (Test-ProjectListener $frontendPort)) {
    Start-Process powershell -WorkingDirectory (Join-Path $workspaceRoot "frontend") -ArgumentList @("-NoExit", "-Command", "npm run dev -- --host 127.0.0.1 --port $frontendPort") | Out-Null
}

Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:$frontendPort/" | Out-Null
Write-Host "SignalForge started: http://127.0.0.1:$frontendPort/"
