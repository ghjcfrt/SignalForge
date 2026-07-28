$ErrorActionPreference = "Stop"

function Get-UvCommand {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        return "uv"
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        try {
            python -m uv --version | Out-Null
            return "python -m uv"
        } catch {}
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            py -m uv --version | Out-Null
            return "py -m uv"
        } catch {}
    }

    throw "uv not found. Please run .\scripts\setup.ps1 first."
}

$port = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8017" }
$uv = Get-UvCommand

if ($uv -eq "uv") {
    & uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port $port
} elseif ($uv -eq "python -m uv") {
    & python -m uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port $port
} else {
    & py -m uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port $port
}
