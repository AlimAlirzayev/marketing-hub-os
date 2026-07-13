# Add ONE Claude subscription account to the rotation store (Windows twin).
# Mirrors scripts/add_claude_account.sh: `claude setup-token` does a browser
# OAuth and PRINTS a long-lived token; we capture it into the private,
# git-ignored store so gateway.claude_bridge can fail over between accounts
# when one hits its 5-hour cap. Run once per account (authorize a different
# Claude account in the browser each time).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$store = Join-Path $root "data\private_context\claude_accounts.json"
$name = if ($args.Count -ge 1) { $args[0] } else { "account-$([int](Get-Date -UFormat %s))" }

Write-Host "-----------------------------------------------"
Write-Host " '$name' hesabini elave edirik."
Write-Host " Cixan linki brauzerde ac, ELAVE etmek istediyin"
Write-Host " Claude hesabi ile tesdiqle."
Write-Host "-----------------------------------------------"

# setup-token prints the URL (you open it) and then the token; capture all output.
$out = (claude setup-token 2>&1 | Tee-Object -Variable _ | Out-String)
$m = [regex]::Match($out, 'sk-ant-oat[A-Za-z0-9_-]+')
if (-not $m.Success) {
    Write-Host "X Token tapilmadi. Yeniden cehd et."
    exit 1
}
$token = $m.Value

New-Item -ItemType Directory -Force -Path (Split-Path $store) | Out-Null
$data = @{ active = 0; accounts = @() }
if (Test-Path $store) {
    try { $data = Get-Content $store -Raw | ConvertFrom-Json } catch {}
}
$accts = @($data.accounts | Where-Object { $_.name -ne $name })
$accts += [pscustomobject]@{ name = $name; token = $token; cooldown_until = 0 }
$data.accounts = $accts
($data | ConvertTo-Json -Depth 6) | Set-Content -Path $store -Encoding UTF8
Write-Host "OK '$name' elave olundu. Cemi hesab: $($accts.Count)"
