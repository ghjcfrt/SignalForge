$ErrorActionPreference = "Stop"

if (Get-Command python -ErrorAction SilentlyContinue) {
    python -m uv run python -m compileall backend
} else {
    py -m uv run python -m compileall backend
}

Push-Location frontend
try {
    npm run build
} finally {
    Pop-Location
}

