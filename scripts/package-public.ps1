Param(
  [string]$DemoFile = "resources/private/demo-provider.json"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path ".").Path
$privatePath = Join-Path $repoRoot "resources/private"
$backupPath = Join-Path $repoRoot "resources/.private-public-package-backup"
$stagedPrivatePath = Join-Path $repoRoot "resources/private"

if (Test-Path $backupPath) {
  throw "Backup path already exists: $backupPath. Remove it before packaging."
}

if (Test-Path $privatePath) {
  Write-Warning "Temporarily quarantining resources/private so the PUBLIC build cannot bundle ignored demo credentials."
  Move-Item -LiteralPath $privatePath -Destination $backupPath
}

try {
  New-Item -ItemType Directory -Force -Path $stagedPrivatePath | Out-Null
  $examplePath = Join-Path $backupPath "demo-provider.example.json"
  if (Test-Path $examplePath) {
    Copy-Item -LiteralPath $examplePath -Destination (Join-Path $stagedPrivatePath "demo-provider.example.json")
  }
  npm.cmd run build:public
  npm.cmd run package --workspace @genie/desktop
  npm.cmd run audit:package
} finally {
  if (Test-Path $backupPath) {
    if (Test-Path $stagedPrivatePath) {
      Remove-Item -Recurse -Force $stagedPrivatePath
    }
    Write-Host "Restoring resources/private after public packaging." -ForegroundColor Cyan
    Move-Item -LiteralPath $backupPath -Destination $privatePath
  }
}
