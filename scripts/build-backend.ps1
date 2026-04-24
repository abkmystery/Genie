Param(
  [string]$Python = "py",
  [string]$PythonVersion = "3.11",
  [string]$OutDir = "resources/backend",
  [string]$Requirements = "services/local-api/requirements.package.txt"
)

$ErrorActionPreference = "Stop"

Write-Host "Building Genie local backend exe (Windows, no-console)..." -ForegroundColor Cyan

$repoRoot = (Resolve-Path ".").Path
$serviceDir = Join-Path $repoRoot "services/local-api"
$outDirAbs = Join-Path $repoRoot $OutDir
$requirementsAbs = Join-Path $repoRoot $Requirements
New-Item -ItemType Directory -Force -Path $outDirAbs | Out-Null

function Stop-LockedBackendProcesses {
  $names = @("genie-local-api", "genie-local-api-console")
  foreach ($n in $names) {
    try {
      Get-Process $n -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    } catch {
      # ignore
    }
  }
}

function Remove-WithRetry {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [int]$Retries = 10
  )

  for ($i = 0; $i -lt $Retries; $i++) {
    try {
      if (Test-Path $Path) {
        Remove-Item -Force $Path -ErrorAction Stop
      }
      return
    } catch {
      Start-Sleep -Milliseconds 300
    }
  }

  # Last attempt with a clearer error
  if (Test-Path $Path) {
    throw "Failed to remove '$Path'. It is likely still in use. Close Genie and try again."
  }
}

Push-Location $serviceDir
try {
  & $Python "-$PythonVersion" -m pip install --upgrade pip | Out-Null
  & $Python "-$PythonVersion" -m pip install -r $requirementsAbs | Out-Null
  & $Python "-$PythonVersion" -m pip install pyinstaller | Out-Null

  $specOut = Join-Path $outDirAbs "genie-local-api.exe"
  $consoleOut = Join-Path $outDirAbs "genie-local-api-console.exe"
  $workOut = Join-Path $outDirAbs "pyinstaller-work"
  $specDir = Join-Path $outDirAbs "pyinstaller-spec"
  Stop-LockedBackendProcesses
  Remove-WithRetry -Path $specOut -Retries 15
  Remove-WithRetry -Path $consoleOut -Retries 15
  if (Test-Path $workOut) { Remove-Item -LiteralPath $workOut -Recurse -Force }
  if (Test-Path $specDir) { Remove-Item -LiteralPath $specDir -Recurse -Force }

  & $Python "-$PythonVersion" -m PyInstaller `
    --noconsole `
    --onefile `
    --clean `
    --name "genie-local-api" `
    --distpath $outDirAbs `
    --workpath (Join-Path $outDirAbs "pyinstaller-work") `
    --specpath (Join-Path $outDirAbs "pyinstaller-spec") `
    --exclude-module "torch" `
    --exclude-module "torchvision" `
    --exclude-module "tensorflow" `
    --exclude-module "transformers" `
    --exclude-module "datasets" `
    --exclude-module "bitsandbytes" `
    --exclude-module "timm" `
    --exclude-module "nltk" `
    --exclude-module "sklearn" `
    --exclude-module "pytest" `
    --exclude-module "reportlab" `
    --exclude-module "matplotlib" `
    --exclude-module "scipy" `
    (Join-Path $serviceDir "app/entrypoint.py") | Out-Null

  Write-Host "Backend built: $specOut" -ForegroundColor Green
} finally {
  Pop-Location
}
