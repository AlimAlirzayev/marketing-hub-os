# ============================================================
# Bulk import n8n workflow templates
# Sources:
#   - enescingoz/awesome-n8n-templates   (280+ templates)
#   - wassupjay/n8n-free-templates        (200+ AI/Vector DB)
# ============================================================

param(
    [string]$BaseDir = "C:\Users\a.alirzayev\ramin-os",
    [switch]$SkipClone
)

$ErrorActionPreference = "Stop"
$tempDir = "$BaseDir\.tmp"
$workflowsDir = "$BaseDir\n8n\workflows"

if (-not (Test-Path $tempDir)) {
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
}

Write-Host "==> n8n template import" -ForegroundColor Cyan
Write-Host ""

$repos = @(
    @{ Url = "https://github.com/enescingoz/awesome-n8n-templates.git"; Path = "awesome-n8n-templates" }
    @{ Url = "https://github.com/wassupjay/n8n-free-templates.git";    Path = "n8n-free-templates" }
)

foreach ($r in $repos) {
    $target = "$tempDir\$($r.Path)"
    if ($SkipClone -and (Test-Path $target)) { continue }
    if (Test-Path $target) {
        Write-Host "==> updating $($r.Path) ..." -ForegroundColor Yellow
        Set-Location $target; git pull; Set-Location $BaseDir
    } else {
        Write-Host "==> cloning $($r.Path) ..." -ForegroundColor Yellow
        git clone --depth 1 $r.Url $target
    }
}

# Category keywords
$categories = @{
    "marketing" = @("marketing", "social", "instagram", "linkedin", "twitter", "facebook", "tiktok", "seo", "content", "email-campaign", "newsletter")
    "business"  = @("crm", "lead", "sales", "invoice", "customer", "support", "ticket", "appointment", "booking", "whatsapp", "telegram")
    "developer" = @("github", "gitlab", "ci", "cd", "deploy", "test", "code-review", "docs", "monitor", "devops", "docker", "k8s")
    "personal"  = @("calendar", "notion", "drive", "todo", "reminder", "weather", "news", "rss", "youtube", "spotify", "personal")
}

$counts = @{}
foreach ($cat in $categories.Keys) { $counts[$cat] = 0 }
$other = 0

Write-Host ""
Write-Host "==> categorizing templates ..." -ForegroundColor Cyan

foreach ($r in $repos) {
    $repoPath = "$tempDir\$($r.Path)"
    if (-not (Test-Path $repoPath)) { continue }
    $jsonFiles = Get-ChildItem -Path $repoPath -Filter "*.json" -Recurse -ErrorAction SilentlyContinue
    foreach ($f in $jsonFiles) {
        $nameLower = $f.Name.ToLower()
        $pathLower = $f.FullName.ToLower()
        $assigned = $false
        foreach ($cat in $categories.Keys) {
            foreach ($kw in $categories[$cat]) {
                if ($nameLower -like "*$kw*" -or $pathLower -like "*\$kw\*") {
                    $dest = "$workflowsDir\$cat\$($f.Name)"
                    if (-not (Test-Path $dest)) {
                        Copy-Item $f.FullName $dest -Force
                        $counts[$cat]++
                    }
                    $assigned = $true
                    break
                }
            }
            if ($assigned) { break }
        }
        if (-not $assigned) {
            $dest = "$workflowsDir\personal\$($f.Name)"
            if (-not (Test-Path $dest)) {
                Copy-Item $f.FullName $dest -Force
                $other++
            }
        }
    }
}

Write-Host ""
Write-Host "==> result:" -ForegroundColor Green
foreach ($cat in $categories.Keys) {
    Write-Host "    $cat`: $($counts[$cat])" -ForegroundColor Green
}
Write-Host "    uncategorized -> personal: $other" -ForegroundColor DarkGray
Write-Host ""
Write-Host "==> done. Open n8n: http://localhost:5678" -ForegroundColor Cyan
Write-Host "    Then: Workflows > Import from File > pick each .json" -ForegroundColor DarkGray
