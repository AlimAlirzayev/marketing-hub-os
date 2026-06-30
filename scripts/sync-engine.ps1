# sync-engine.ps1 - pull the latest shared ENGINE (code, tools, capabilities) safely.
# Run this on startup (the "button"). It only fast-forwards the engine; PRIVATE data
# (.env, data/, private context - all git-ignored) is never touched or shared.
# ASCII-only for Windows PowerShell 5.1.

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$env:GIT_SSH_COMMAND = "ssh -o StrictHostKeyChecking=accept-new"

Write-Output "Syncing engine from origin (shared code/tools only)..."
git fetch origin

$dirty = git status --porcelain
if ($dirty) {
  Write-Output "NOTE: you have uncommitted local changes. Commit them before/after a sync."
}

try {
  $local  = (git rev-parse "@").Trim()
  $remote = (git rev-parse "@{u}").Trim()
  $base   = (git merge-base "@" "@{u}").Trim()
} catch {
  Write-Output "No upstream set. Run once: git push -u origin master"
  exit 1
}

if ($local -eq $remote) {
  Write-Output "Already up to date - no new engine updates."
} elseif ($local -eq $base) {
  Write-Output "New engine updates found. Applying (fast-forward only)..."
  git pull --ff-only
  Write-Output "Engine updated. Private data untouched."
} elseif ($remote -eq $base) {
  Write-Output "You have local engine commits not pushed yet. Run: git push origin master"
} else {
  Write-Output "Branches diverged - manual review needed (no automatic merge)."
}
