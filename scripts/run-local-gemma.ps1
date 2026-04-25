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

$verifyScript = @'
try:
    import transformers
    from transformers import AutoModelForMultimodalLM
    print(f"Transformers ready: {transformers.__version__}")
except Exception as exc:
    raise SystemExit(
        "This Python environment does not have Gemma 4 multimodal support. "
        "Run npm.cmd run setup:local-gemma, then try again. "
        f"Details: {type(exc).__name__}: {exc}"
    )
'@
$verifyPath = Join-Path ([System.IO.Path]::GetTempPath()) "genie-verify-local-gemma.py"
Set-Content -LiteralPath $verifyPath -Value $verifyScript -Encoding UTF8
try {
  & $Python "-$PythonVersion" $verifyPath
} finally {
  Remove-Item -LiteralPath $verifyPath -Force -ErrorAction SilentlyContinue
}

& $Python "-$PythonVersion" -m uvicorn app:app --app-dir services/local-gemma-runner --host 127.0.0.1 --port 8766
