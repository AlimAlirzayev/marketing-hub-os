# Research Lab — avtonom, qapılı bilik bazası

Alim-in marketing co-pilotu üçün fonda öyrənən laboratoriya. Hər 3 gündə bir işləyir,
ən son kreativ/AI marketing siqnalını araşdırır, **keyfiyyət qapısından** (LLM-as-judge)
keçirir, yalnız siqnalı markdown bazaya yazır və Telegram-a qısa digest göndərir.

## Dizayn prinsipləri (niyə bu, 2026-05-19-da dəfn etdiyimiz loop deyil)
1. **Keyfiyyət qapısı** — `lab.py` araşdırmanı ikinci bir modelə (judge) verir; yalnız
   `min_score`-dan yuxarı, təkrar olmayan tapıntılar bazaya düşür. Zibil girmir.
2. **Xərc/run tavanı** — `max_runs_per_month` aşılsa run keçilir.
3. **Yalnız xəbər ver / bazaya yaz** — heç vaxt müştəri işinə tətbiq etmir.
4. **Kill-switch** — `touch /opt/research-lab/KILL` → dayanır. `rm KILL` → işə düşür.
5. **Heç vaxt səssiz** — hər run (uğur və ya xəta) Telegram-a artefakt qoyur + `logs/`.

## Struktur
- `lab.py` — əsas skript (research → judge → store → notify).
- `config.json` — missiya, modellər, qapı həddi, run tavanı.
- `knowledge/` — böyüyən bilik bazası (hər tapıntı = bir .md) + `INDEX.md`.
- `logs/` — günlük loglar (observability).
- `ledger.json` — run tarixçəsi + token istifadəsi (xərc izləmə).
- `KILL` — varsa sistem dayanır (söndürücü).

## İdarəetmə
```bash
# Əl ilə bir run (test):
python3 /opt/research-lab/lab.py

# Söndür / işə sal:
touch /opt/research-lab/KILL
rm    /opt/research-lab/KILL

# Cron (hər 3 gündə, Baku 10:00 ≈ 06:00 UTC):
0 6 */3 * * /usr/bin/python3 /opt/research-lab/lab.py
```

## NotebookLM bağlantısı (recall qatı)
`knowledge/` korpusu zaman-zaman NotebookLM notebook-una mənbə kimi əlavə olunur;
Alim soruşanda Mac-də `notebooklm` skill ilə sitatlı, hazır cavab alınır.
