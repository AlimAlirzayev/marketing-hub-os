# sync-engine.ps1 - the startup "button": pull the latest shared ENGINE and push
# your committed engine commits, safely. All logic lives in ONE place
# (scripts/sync_engine.py) so the PC, Mac, and VPS behave identically.
# PRIVATE data (.env, data/, private context) is git-ignored -> never touched.
# ASCII-only for Windows PowerShell 5.1.

$ErrorActionPreference = "SilentlyContinue"
$brain = Join-Path $PSScriptRoot "sync_engine.py"
python $brain @args
