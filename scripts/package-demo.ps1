Param(
  [string]$DemoFile = "resources/private/demo-provider.json"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path ".").Path
$demoPath = Join-Path $repoRoot $DemoFile
$privatePath = Join-Path $repoRoot "resources/private"
$backupPath = Join-Path $repoRoot "resources/.private-demo-package-backup"
$stagedPrivatePath = Join-Path $repoRoot "resources/private"

if (-not (Test-Path $demoPath)) {
  Write-Warning "No $DemoFile found. Demo mode will fall back to offline/mock in the packaged app."
} else {
  Write-Host "Using $DemoFile for the DEMO build (it will be bundled into the packaged app resources)." -ForegroundColor Cyan
}

if (Test-Path $backupPath) {
  throw "Backup path already exists: $backupPath. Remove it before packaging."
}

if (Test-Path $privatePath) {
  Write-Host "Staging only the single demo credential file for the DEMO package." -ForegroundColor Cyan
  Move-Item -LiteralPath $privatePath -Destination $backupPath
}

try {
  New-Item -ItemType Directory -Force -Path $stagedPrivatePath | Out-Null
  $examplePath = Join-Path $backupPath "demo-provider.example.json"
  if (Test-Path $examplePath) {
    Copy-Item -LiteralPath $examplePath -Destination (Join-Path $stagedPrivatePath "demo-provider.example.json")
  }
  $realDemoPath = Join-Path $backupPath "demo-provider.json"
  if (Test-Path $realDemoPath) {
    Copy-Item -LiteralPath $realDemoPath -Destination (Join-Path $stagedPrivatePath "demo-provider.json")
  }

  npm.cmd run build:demo
  npm.cmd run package --workspace @genie/desktop
  npm.cmd run audit:package -- -AllowDemoCredential
} finally {
  if (Test-Path $backupPath) {
    if (Test-Path $stagedPrivatePath) {
      Remove-Item -Recurse -Force $stagedPrivatePath
    }
    Write-Host "Restoring resources/private after demo packaging." -ForegroundColor Cyan
    Move-Item -LiteralPath $backupPath -Destination $privatePath
  }
}
