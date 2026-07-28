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

    throw "uv not found. Please install uv or ensure python -m uv is available."
}

function Invoke-Uv {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    $uv = Get-UvCommand
    if ($uv -eq "uv") {
        & uv @Arguments
    } elseif ($uv -eq "python -m uv") {
        & python -m uv @Arguments
    } else {
        & py -m uv @Arguments
    }
}

Write-Host "==> Sync Python dependencies into uv virtualenv .venv"
Invoke-Uv sync

Write-Host "==> Install frontend dependencies"
Push-Location frontend
try {
    npm install
} finally {
    Pop-Location
}

Write-Host "==> Done. Start backend with .\scripts\dev-backend.ps1 and frontend with .\scripts\dev-frontend.ps1"
