#!/usr/bin/env bash
# sync-engine.sh - pull the latest shared ENGINE (code, tools, capabilities) safely.
# Run on startup (the "button"). Only fast-forwards the engine; PRIVATE data
# (.env, data/, private context - all git-ignored) is never touched or shared.
set -e
cd "$(dirname "$0")/.."
export GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new"

echo "Syncing engine from origin (shared code/tools only)..."
git fetch origin

if [ -n "$(git status --porcelain)" ]; then
  echo "NOTE: you have uncommitted local changes. Commit them before/after a sync."
fi

LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse @{u} 2>/dev/null) || { echo "No upstream set. Run once: git push -u origin master"; exit 1; }
BASE=$(git merge-base @ @{u})

if [ "$LOCAL" = "$REMOTE" ]; then
  echo "Already up to date - no new engine updates."
elif [ "$LOCAL" = "$BASE" ]; then
  echo "New engine updates found. Applying (fast-forward only)..."
  git pull --ff-only
  echo "Engine updated. Private data untouched."
elif [ "$REMOTE" = "$BASE" ]; then
  echo "You have local engine commits not pushed yet. Run: git push origin master"
else
  echo "Branches diverged - manual review needed (no automatic merge)."
fi
