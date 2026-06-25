**Checkpoint — kredensial əldə etmə təsdiq tələb edir.**

Provider: `rapidapi`

Credential acquisition needs explicit operator approval (set GATEWAY_ALLOW_CREDENTIALS=1) and a one-time interactive browser login. It is never run silently in the background.

Bu, fonda səssiz işləmir (bir dəfəlik brauzer login lazımdır). İcazə üçün:
1. `.env`-də `GATEWAY_ALLOW_CREDENTIALS=1` təyin et, **və ya**
2. birbaşa işə sal:  `.venv\Scripts\python -m doit rapidapi`

Açar `.env`-ə yazılacaq və heç bir yerdə ifşa olunmayacaq.