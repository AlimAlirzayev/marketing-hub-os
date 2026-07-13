#!/bin/bash
# Add ONE Claude subscription account to the rotation store.
#
# `claude setup-token` does a browser OAuth and PRINTS a long-lived token (it
# does not write a creds file). This captures that token straight into the
# private, git-ignored rotation store so gateway.claude_bridge can fail over
# between accounts when one hits its 5-hour usage cap. Run once per account,
# authorizing a DIFFERENT Claude account in the browser each time.
#
# Usage: scripts/add_claude_account.sh [account-name]
set -euo pipefail
cd "$(dirname "$0")/.."

NAME="${1:-account-$(date +%s)}"
STORE="data/private_context/claude_accounts.json"

echo "———————————————————————————————————————————————"
echo " '$NAME' hesabını əlavə edirik."
echo " Aşağıda bir link çıxacaq → brauzerdə AÇ, ƏLAVƏ etmək"
echo " istədiyin Claude hesabı ilə təsdiqlə."
echo "———————————————————————————————————————————————"

# tee /dev/tty shows the URL live (so you can open it) while we capture output.
OUT="$(claude setup-token 2>&1 | tee /dev/tty)"
TOKEN="$(printf '%s' "$OUT" | grep -oE 'sk-ant-oat[A-Za-z0-9_-]+' | head -1 || true)"

if [ -z "$TOKEN" ]; then
  echo
  echo "❌ Token tapılmadı. Yenidən cəhd et (linki brauzerdə tam təsdiqlə)."
  exit 1
fi

python3 - "$NAME" "$TOKEN" "$STORE" <<'PY'
import json, os, sys
name, token, store = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(os.path.dirname(store), exist_ok=True)
data = {"active": 0, "accounts": []}
if os.path.exists(store):
    try: data = json.load(open(store))
    except Exception: pass
data["accounts"] = [a for a in data.get("accounts", []) if a.get("name") != name]
data["accounts"].append({"name": name, "token": token, "cooldown_until": 0})
json.dump(data, open(store, "w"))
os.chmod(store, 0o600)
print(f"\n✅ '{name}' əlavə olundu. Cəmi hesab: {len(data['accounts'])}")
PY

echo "Beyin artıq bu hesab(lar)dan istifadə edəcək. Telegram-dan yaz və yoxla."
