Param(
  [string]$Python = "py",
  [string]$PythonVersion = "3.11",
  [string]$ModelId = "google/gemma-4-E4B-it",
  [string]$ModelDir = ""
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path ".").Path
$runnerDir = Join-Path $repoRoot "services/local-gemma-runner"
$safeModelName = (($ModelId -replace '^google/', '') -replace '[^A-Za-z0-9_.-]', '-')
if (-not $ModelDir) {
  $ModelDir = "models/$safeModelName"
}
$modelDirAbs = if ([System.IO.Path]::IsPathRooted($ModelDir)) { $ModelDir } else { Join-Path $repoRoot $ModelDir }

Write-Host "Setting up experimental local Gemma 4 runner..." -ForegroundColor Cyan
Write-Host "Model: $ModelId"
Write-Host "Target: $modelDirAbs"

& $Python "-$PythonVersion" -m pip install --upgrade pip
& $Python "-$PythonVersion" -m pip install -r (Join-Path $runnerDir "requirements.txt")
Write-Host "Installing latest Hugging Face Transformers with Gemma 4 multimodal support..." -ForegroundColor Cyan
& $Python "-$PythonVersion" -m pip install --upgrade --force-reinstall "transformers @ git+https://github.com/huggingface/transformers.git"
& $Python "-$PythonVersion" -m pip install "huggingface_hub[cli]"

$verifyScript = @'
import importlib.metadata as metadata
import sys

try:
    import transformers
    from transformers import AutoModelForMultimodalLM, AutoProcessor
except Exception as exc:
    raise SystemExit(f"Gemma 4 Transformers verification failed: {type(exc).__name__}: {exc}")

print("Transformers:", metadata.version("transformers"))
print("Gemma 4 multimodal class:", AutoModelForMultimodalLM.__name__)
print("AutoProcessor:", AutoProcessor.__name__)
'@
& $Python "-$PythonVersion" -c $verifyScript

New-Item -ItemType Directory -Force -Path $modelDirAbs | Out-Null
& $Python "-$PythonVersion" -m huggingface_hub.commands.huggingface_cli download $ModelId --local-dir $modelDirAbs --local-dir-use-symlinks False

Write-Host ""
Write-Host "Local Gemma 4 model downloaded." -ForegroundColor Green
Write-Host "Next: npm.cmd run dev:local-gemma"
