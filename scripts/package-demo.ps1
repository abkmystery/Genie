Param(
  [string]$DemoFile = "resources/private/demo-provider.json"
)

$ErrorActionPreference = "Stop"
$demoPath = Join-Path (Resolve-Path ".").Path $DemoFile

if (-not (Test-Path $demoPath)) {
  Write-Warning "No $DemoFile found. Demo mode will fall back to offline/mock in the packaged app."
} else {
  Write-Host "Using $DemoFile for the DEMO build (it will be bundled into the packaged app resources)." -ForegroundColor Cyan
}

npm.cmd run build:demo
npm.cmd run package --workspace @genie/desktop
npm.cmd run audit:package -- -AllowDemoCredential
