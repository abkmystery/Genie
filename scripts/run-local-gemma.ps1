Param(
  [string]$Python = "py",
  [string]$PythonVersion = "3.11",
  [string]$ModelId = "google/gemma-4-E4B-it",
  [string]$ModelDir = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path ".").Path
if (-not $ModelDir) {
  $safeModelName = (($ModelId -replace '^google/', '') -replace '[^A-Za-z0-9_.-]', '-')
  $ModelDir = Join-Path $repoRoot "models/$safeModelName"
} elseif (-not [System.IO.Path]::IsPathRooted($ModelDir)) {
  $ModelDir = Join-Path $repoRoot $ModelDir
}

if (-not (Test-Path -LiteralPath $ModelDir)) {
  throw "Model folder not found: $ModelDir"
}

$env:GENIE_LOCAL_MODEL_ID = $ModelId
$env:GENIE_LOCAL_MODEL_DIR = (Resolve-Path -LiteralPath $ModelDir).Path

Write-Host "Starting local Gemma runner..." -ForegroundColor Cyan
Write-Host "Model id:  $env:GENIE_LOCAL_MODEL_ID"
Write-Host "Model dir: $env:GENIE_LOCAL_MODEL_DIR"

& $Python "-$PythonVersion" -m uvicorn app:app --app-dir services/local-gemma-runner --host 127.0.0.1 --port 8766
