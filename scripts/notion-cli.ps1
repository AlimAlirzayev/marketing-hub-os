param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$PortableNode = Get-ChildItem -Path (Join-Path $RepoRoot "video-studio\tools") -Recurse -Filter "node.exe" -ErrorAction SilentlyContinue |
    Sort-Object FullName -Descending |
    Select-Object -First 1
$NtnCommand = Join-Path $RepoRoot ".tools\notion-cli\ntn.cmd"

if ($PortableNode) {
    $env:Path = "$(Split-Path -Parent $PortableNode.FullName);$env:Path"
}

if (-not (Test-Path $NtnCommand)) {
    Write-Error "Notion CLI is not installed at $NtnCommand. Run .\scripts\setup-notion-workers.ps1 first."
}

& $NtnCommand @Args
exit $LASTEXITCODE
