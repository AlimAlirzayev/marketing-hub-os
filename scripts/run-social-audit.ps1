param(
  [string]$Manifest = "social-studio\audit\manifests\xalqsigorta-travel-insurance.json",
  [string]$Rubric = "social-studio\audit\rubric.json",
  [string]$OutDir = "output\social\audit"
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
  python social-studio\audit\creative_audit.py `
    --manifest $Manifest `
    --rubric $Rubric `
    --out-dir $OutDir
}
finally {
  Pop-Location
}
