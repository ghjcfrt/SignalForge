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
        if (-not $process) { continue }
        $commandLine = [string]$process.CommandLine
        # Vite may be started from `frontend`, so its command line can contain
        # a relative path and omit the absolute workspace root. Treat the
        # project Vite command as ours when it also carries this port.
        if ($commandLine -like "*$workspaceRoot*") { return $true }
        if ($port -eq $backendPort -and
            $commandLine -match '(?i)(uvicorn|uvicorn\.exe|python\.exe|python)\b' -and
            $commandLine -match '(?i)backend\.app\.main:app' -and
            $commandLine -match "(?i)(--port\s+)?$port(\s|$)") { return $true }
        if ($port -eq $frontendPort -and
            $commandLine -match '(?i)(vite|vite\.js)' -and
            $commandLine -match '(?i)(^|[\\/ ])frontend([\\/ ]|$)' -and
            $commandLine -match "(?i)(--port\s+)?$port(\s|$)") { return $true }
    }
    return $false
}

function Get-FrontendListener([int]$port) {
    $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if (-not $process) { continue }
        $commandLine = [string]$process.CommandLine
        if ($commandLine -notmatch '(?i)(vite|vite\.js)' -or
            $commandLine -notmatch "(?i)(--port\s+)?$port(\s|$)") { continue }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/" -TimeoutSec 2
            if ($response.StatusCode -eq 200 -and
                ([string]$response.Content -match 'id=["'']root["'']|src/main\.tsx')) {
                return $true
            }
        } catch {}
    }
    return $false
}

function Stop-StaleFrontend([int]$port) {
    $listeners = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        $commandLine = [string]$process.CommandLine
        if ($process -and $commandLine -match '(?i)(vite|vite\.js)' -and
            $commandLine -match '(?i)(frontend[\\/]node_modules|node_modules[\\/]vite)' -and
            $commandLine -match "(?i)(--port\s+)?$port(\s|$)") {
            Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}


foreach ($port in @($backendPort, $frontendPort)) {
    if ((Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) -and -not (Test-ProjectListener $port)) {
        throw "Port $port is already in use by another process."
    }
}

$uv = Get-UvCommand
if (-not (Test-ProjectListener $backendPort)) {
    $backendCommand = "$uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port $backendPort"
    Start-Process powershell -WorkingDirectory $workspaceRoot -ArgumentList @("-NoExit", "-Command", $backendCommand) | Out-Null
}
if (-not (Get-FrontendListener $frontendPort)) {
    Stop-StaleFrontend $frontendPort
    $node = Get-Command node.exe -ErrorAction SilentlyContinue
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($npm) {
        $frontendCommand = "npm run dev -- --host 127.0.0.1 --port $frontendPort"
    } elseif ($node) {
        $frontendCommand = "node node_modules/vite/bin/vite.js --host 127.0.0.1 --port $frontendPort"
    } else {
        $bundledNode = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe"
        if (-not (Test-Path -LiteralPath $bundledNode)) {
            throw "Node.js not found. Install Node.js or run the project with its bundled runtime."
        }
        $frontendCommand = "& '$bundledNode' node_modules/vite/bin/vite.js --root '$workspaceRoot\frontend' --host 127.0.0.1 --port $frontendPort"
    }
    Start-Process powershell -WorkingDirectory (Join-Path $workspaceRoot "frontend") -ArgumentList @("-NoExit", "-Command", $frontendCommand) | Out-Null
}

Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:$frontendPort/" | Out-Null
Write-Host "SignalForge started: http://127.0.0.1:$frontendPort/"
