# ============================================================
# Install Claude Code subagents and skills
# Sources:
#   - VoltAgent/awesome-claude-code-subagents   (100+ specialized subagents)
#   - alirezarezvani/awesome-claude-code-skills  (community skill library)
# Idempotent: skips repos that are already cloned.
# ============================================================

param(
    [string]$BaseDir = "C:\Users\a.alirzayev\ramin-os",
    [switch]$Update
)

$ErrorActionPreference = "Stop"

$tempDir   = "$BaseDir\.tmp"
$agentsDir = "$BaseDir\claude-agents\.claude\agents"
$skillsDir = "$BaseDir\claude-agents\.claude\skills"

foreach ($d in @($tempDir, $agentsDir, $skillsDir)) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
    }
}

Write-Host "==> Claude Code agents and skills install" -ForegroundColor Cyan
Write-Host ""

$repos = @(
    @{ Url = "https://github.com/VoltAgent/awesome-claude-code-subagents.git"; Path = "awesome-claude-code-subagents"; Kind = "agents" }
    @{ Url = "https://github.com/alirezarezvani/awesome-claude-code-skills.git"; Path = "awesome-claude-code-skills";   Kind = "skills" }
)

foreach ($r in $repos) {
    $target = "$tempDir\$($r.Path)"
    if (Test-Path $target) {
        if ($Update) {
            Write-Host "==> updating $($r.Path) ..." -ForegroundColor Yellow
            Set-Location $target; git pull; Set-Location $BaseDir
        } else {
            Write-Host "==> $($r.Path) already cloned (use -Update to refresh)" -ForegroundColor DarkGray
        }
    } else {
        Write-Host "==> cloning $($r.Path) ..." -ForegroundColor Yellow
        git clone --depth 1 $r.Url $target
    }
}

Write-Host ""
Write-Host "==> copying agent and skill definitions ..." -ForegroundColor Cyan

$agentCount = 0
$skillCount = 0

# Subagents: VoltAgent stores agent markdown files across category folders
$agentSrc = "$tempDir\awesome-claude-code-subagents"
if (Test-Path $agentSrc) {
    $mdFiles = Get-ChildItem -Path $agentSrc -Filter "*.md" -Recurse -ErrorAction SilentlyContinue |
               Where-Object { $_.Name -notmatch '^(README|LICENSE|CONTRIBUTING|CODE_OF_CONDUCT)' }
    foreach ($f in $mdFiles) {
        $dest = "$agentsDir\$($f.Name)"
        if (-not (Test-Path $dest)) {
            Copy-Item $f.FullName $dest -Force
            $agentCount++
        }
    }
}

# Skills: each skill is usually a folder containing a SKILL.md
$skillSrc = "$tempDir\awesome-claude-code-skills"
if (Test-Path $skillSrc) {
    $skillDirs = Get-ChildItem -Path $skillSrc -Directory -Recurse -ErrorAction SilentlyContinue |
                 Where-Object { Test-Path "$($_.FullName)\SKILL.md" }
    foreach ($d in $skillDirs) {
        $dest = "$skillsDir\$($d.Name)"
        if (-not (Test-Path $dest)) {
            Copy-Item $d.FullName $dest -Recurse -Force
            $skillCount++
        }
    }
}

Write-Host ""
Write-Host "==> result:" -ForegroundColor Green
Write-Host "    subagents installed: $agentCount" -ForegroundColor Green
Write-Host "    skills installed:    $skillCount" -ForegroundColor Green
Write-Host ""
Write-Host "==> done. Agents: $agentsDir" -ForegroundColor Cyan
Write-Host "          Skills: $skillsDir" -ForegroundColor Cyan
