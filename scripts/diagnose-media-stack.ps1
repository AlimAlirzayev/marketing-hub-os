param(
  [string]$SampleAsset = "output\kasko-qurban-2026-meta-reels-FINAL-1080x1920.mp4",
  [string]$Platforms = "instagram,linkedin"
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Section($Name) {
  Write-Host ""
  Write-Host "== $Name =="
}

function EnvStatus($Key) {
  $value = [Environment]::GetEnvironmentVariable($Key, "Process")
  if (-not $value -and (Test-Path ".env")) {
    $line = Get-Content ".env" | Where-Object { $_ -match "^$Key\s*=" } | Select-Object -First 1
    if ($line) { $value = ($line -split "=", 2)[1].Trim() }
  }
  $configured = -not [string]::IsNullOrWhiteSpace($value) -and
    -not $value.StartsWith("your_") -and
    -not $value.StartsWith("<") -and
    $value -ne "changeme"
  [pscustomobject]@{ Key = $Key; Configured = $configured }
}

Section "Environment Keys"
$keys = @(
  "POSTIZ_API_URL",
  "POSTIZ_API_KEY",
  "GROQ_API_KEY",
  "GOOGLE_API_KEY",
  "ELEVENLABS_API_KEY",
  "HF_TOKEN",
  "OPENAI_API_KEY",
  "ANTHROPIC_API_KEY"
)
$keys | ForEach-Object { EnvStatus $_ } | Format-Table -AutoSize

Section "Docker"
try {
  docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
} catch {
  Write-Host "Docker unavailable: $($_.Exception.Message)"
}

Section "Postiz"
try {
  $status = (Invoke-WebRequest -Uri "http://localhost:5000" -UseBasicParsing -TimeoutSec 5).StatusCode
  Write-Host "Postiz reachable: HTTP $status"
} catch {
  Write-Host "Postiz unreachable: $($_.Exception.Message)"
}

Section "Audio Studio"
python audio-studio\audio_studio.py doctor

Section "Publisher Dry Run"
if (Test-Path $SampleAsset) {
  python publisher\run.py $SampleAsset --to $Platforms --dry-run
} else {
  Write-Host "Sample asset not found: $SampleAsset"
}
