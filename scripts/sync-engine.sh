#!/usr/bin/env bash
# sync-engine.sh - the startup "button": pull the latest shared ENGINE and push
# your committed engine commits, safely. All logic lives in ONE place
# (scripts/sync_engine.py) so the PC, Mac, and VPS behave identically.
# PRIVATE data (.env, data/, private context) is git-ignored -> never touched.
here="$(cd "$(dirname "$0")" && pwd)"
py="$(command -v python3 || command -v python)"
exec "$py" "$here/sync_engine.py" "$@"
