Param(
  [switch]$AllowDemoCredential,
  [string]$ReleaseDir = "apps/desktop/release"
)

$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path ".").Path
$releasePath = Join-Path $repoRoot $ReleaseDir

if (-not (Test-Path $releasePath)) {
  Write-Warning "No release directory found at $releasePath. Build/package first to audit packaged artifacts."
  exit 0
}

$unsafePatterns = @(
  "*.env",
  "*.db",
  "*.sqlite",
  "*.sqlite3",
  "*.pyc",
  "*.pyo",
  "*.safetensors",
  "*.ckpt",
  "*.onnx"
)

$unsafeNameRegexes = @(
  "\\__pycache__\\",
  "\\captures\\",
  "\\models\\",
  "\\private\\.*demo-provider\.json\.txt$",
  "\\private\\.*demo-provider\.txt$"
)

if (-not $AllowDemoCredential) {
  $unsafeNameRegexes += "\\private\\.*demo-provider\.json$"
}

$findings = New-Object System.Collections.Generic.List[string]

Get-ChildItem -LiteralPath $releasePath -Recurse -File -Force | ForEach-Object {
  $relative = $_.FullName.Substring($releasePath.Length).TrimStart([char[]]@("\", "/"))
  foreach ($pattern in $unsafePatterns) {
    if ($_.Name -like $pattern) {
      $findings.Add($relative)
    }
  }
  foreach ($regex in $unsafeNameRegexes) {
    if ($_.FullName -match $regex) {
      $findings.Add($relative)
    }
  }
}

if ($findings.Count -gt 0) {
  Write-Error ("Package audit failed. Unsafe artifacts found:`n" + (($findings | Sort-Object -Unique) -join "`n"))
}

Write-Host "Package audit passed for $releasePath" -ForegroundColor Green
