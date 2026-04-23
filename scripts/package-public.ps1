Param(
  [string]$DemoFile = "resources/private/demo-provider.json"
)

$ErrorActionPreference = "Stop"

$demoPath = Join-Path (Resolve-Path ".").Path $DemoFile
$backupPath = "$demoPath.bak"

if (Test-Path $demoPath) {
  Write-Warning "Found $DemoFile. Temporarily moving it out so the PUBLIC build does not bundle your demo key."
  if (Test-Path $backupPath) { Remove-Item -Force $backupPath }
  Rename-Item -Path $demoPath -NewName (Split-Path $backupPath -Leaf)
}

try {
  npm.cmd run build:public
  npm.cmd run package --workspace @genie/desktop
} finally {
  if (Test-Path $backupPath) {
    Write-Host "Restoring $DemoFile after packaging." -ForegroundColor Cyan
    Rename-Item -Path $backupPath -NewName (Split-Path $demoPath -Leaf)
  }
}

