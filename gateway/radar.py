"""AI Radar — bütün AI mənzərəsinin avtonom müşahidəsi (həftəlik brif + günlük nəbz).

Vendor-agnostic BY DESIGN: Google yalnız mənbələrdən biridir. Radar şəkil
(Flux, gpt-image, Ideogram, Nano Banana...), video (Sora, Kling, Runway,
Seedance, Veo...), səs (ElevenLabs, Suno...) və agent-alət (MCP, n8n...)
xəttlərinin HAMISINI izləyir.

İki takt:
  - run()   — HƏFTƏLİK dərin brif: bütün mənbələr → pulsuz LLM həzmi →
              Telegram + data/radar/ + capabilities.md + brain korpusu.
  - pulse() — GÜNDƏLİK yüngül nəbz: sürətli mənbələr (Telegram xəbər kanalları,
              HF trending) → yalnız GERÇƏKDƏN kritik bir şey varsa sahibə ani
              xəbərdarlıq; sakit gündə heç kim narahat olunmur, amma sistem bilir.

Mənbələr pulsuz və açarsız (hamısı qorunur; yıxılanlar brifdə ƏLÇATMAZ kimi
göstərilir — səssiz itki yoxdur):
  - Telegram açıq xəbər kanalları (t.me/s/<kanal> web önizləməsi, açarsız)
  - Hugging Face trending models + daily papers (açıq API)
  - GitHub: son 7 gündə yaranmış ulduzlu AI repoları (açıq axtarış API-si)
  - GitLab: AI mövzulu aktiv layihələr (açıq API)
  - Lab blogları RSS: OpenAI, Google AI, Hugging Face, ElevenLabs, Stability

Brif brain korpusuna da damcılanır — beləcə EXISTING recall yolu
(knowledge.recall_context) istənilən yeni tapşırıqda lab tapıntılarını
avtomatik xatırladır: "siqnal gələn kimi lab-a bax" dövrəsinin halqası.

Grounding qaydası: radar yalnız KƏŞF edir və təklif verir. Təklif real build-ə
çevriləndə docs/CONTEXT7_GROUNDING.md qüvvədədir — Context7 / Hugging Face MCP
sənədləri, GitHub/GitLab mənbə kodu, higgsfield kimi qoşulmuş organlar üzərindən
əsaslandırılır; son qərar həmişə operatorundur.

VACİB ƏMƏLİYYAT QAYDASI: bu repoda cross-machine sync sərt sıfırlayır —
yeni orqan DƏRHAL commit olunmalıdır, yoxsa növbəti sync silir.
"""

from __future__ import annotations

import datetime as _dt
import html as _html
import json
import os
import re as _re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

_ROOT = Path(__file__).resolve().parent.parent
_RADAR_DIR = _ROOT / "data" / "radar"
_LAST_RUN = _RADAR_DIR / "last_run.txt"
_LAST_PULSE = _RADAR_DIR / "last_pulse.txt"
_CAPABILITIES = _ROOT / "claude-agents" / ".claude" / "capabilities.md"
_UA = {"User-Agent": "Mozilla/5.0 (ramin-os-ai-radar/2.0)"}
_TIMEOUT = 25

# Açıq Telegram xəbər kanalları — t.me/s/<kanal> girişi açar tələb etmir.
# Yeni kanal əlavə etmək = bu siyahıya bir ad yazmaq.
_TG_CHANNELS = ["perplexity"]

_RSS_FEEDS = [
    ("OpenAI", "https://openai.com/news/rss.xml"),
    ("Google AI", "https://blog.google/technology/ai/rss/"),
    ("HuggingFace Blog", "https://huggingface.co/blog/feed.xml"),
    ("ElevenLabs", "https://elevenlabs.io/blog/rss.xml"),
    ("Stability", "https://stability.ai/news?format=rss"),
]

# Həzm zamanı modelə verilən orqan xəritəsi — təkliflər bura calanmalıdır.
_ORGANS = (
    "social-studio (şəkil/post), mediaforge (video, FLORA üstündən Seedance/"
    "Kling/Runway/Sora/Veo), audio-studio (səs/TTS/musiqi), copy-studio (mətn səsi), "
    "seo (audit/kontent), ads-studio (Meta performans), price-hunter (qiymət kəşfiyyatı), "
    "influencer-hunter, meta-capi (konversiya göndərişi), doit (kredensial), "
    "gateway (Telegram+queue+council), llm_router (bütün modellər)"
)


def _get_json(url: str, headers: dict | None = None):
    h = dict(_UA)
    if headers:
        h.update(headers)
    r = requests.get(url, headers=h, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _telegram_channel(ch: str, limit: int = 6) -> list[dict]:
    """Açıq kanalın son mesajları — açarsız web önizləmədən.

    Korporativ DNS bəzən t.me-ni bloklayır (telegram.me isə açıq qalır),
    ona görə hostlar növbə ilə sınanır; ikisi də yıxılsa JSON körpüsünə düşür.
    """
    last_err: Exception | None = None
    for host in ("t.me", "telegram.me"):
        try:
            r = requests.get("https://%s/s/%s" % (host, ch), headers=_UA, timeout=_TIMEOUT)
            r.raise_for_status()
            blocks = _re.findall(
                r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', r.text, _re.S
            )
            out = []
            for b in blocks[-limit:]:
                text = _re.sub(r"<br\s*/?>", " ", b)
                text = _re.sub(r"<[^>]+>", "", text)
                text = _html.unescape(_re.sub(r"\s+", " ", text)).strip()
                if text:
                    out.append({"src": "TG @%s" % ch, "title": text[:220], "info": "",
                                "url": "https://t.me/s/%s" % ch})
            if out:
                return out
        except Exception as exc:  # noqa: BLE001 — növbəti hosta keç
            last_err = exc
    try:  # son çarə: açıq JSON körpüsü
        data = _get_json("https://tg.i-c-a.su/json/%s?limit=%d" % (ch, limit))
        msgs = data.get("messages", data if isinstance(data, list) else [])
        out = []
        for m in msgs[:limit]:
            text = (m.get("message") or "").strip()
            if text:
                out.append({"src": "TG @%s" % ch, "title": text[:220], "info": "",
                            "url": "https://t.me/s/%s" % ch})
        if out:
            return out
    except Exception as exc:  # noqa: BLE001
        last_err = exc
    raise last_err or RuntimeError("kanal oxuna bilmədi: %s" % ch)


def _hf_models(limit: int = 10) -> list[dict]:
    data = _get_json(
        "https://huggingface.co/api/models?sort=trendingScore&direction=-1&limit=%d" % limit
    )
    return [
        {"src": "HF trending", "title": m.get("id", "?"),
         "info": (m.get("pipeline_tag") or ""),
         "url": "https://huggingface.co/" + m.get("id", "")}
        for m in data
    ]


def _hf_papers(limit: int = 6) -> list[dict]:
    data = _get_json("https://huggingface.co/api/daily_papers?limit=%d" % limit)
    out = []
    for p in data[:limit]:
        paper = p.get("paper") or {}
        out.append({
            "src": "HF papers", "title": paper.get("title", "?"), "info": "",
            "url": "https://huggingface.co/papers/" + str(paper.get("id", "")),
        })
    return out


def _github_new(limit: int = 8) -> list[dict]:
    since = (_dt.date.today() - _dt.timedelta(days=7)).isoformat()
    headers = {}
    tok = os.getenv("GITHUB_TOKEN")
    if tok:
        headers["Authorization"] = "Bearer " + tok
    data = _get_json(
        "https://api.github.com/search/repositories?q=topic:ai+created:%%3E%s&sort=stars&order=desc&per_page=%d"
        % (since, limit),
        headers=headers,
    )
    return [
        {"src": "GitHub yeni", "title": it.get("full_name", "?"),
         "info": (it.get("description") or "")[:120] + " (★%s)" % it.get("stargazers_count", 0),
         "url": it.get("html_url", "")}
        for it in data.get("items", [])
    ]


def _gitlab_new(limit: int = 5) -> list[dict]:
    data = _get_json(
        "https://gitlab.com/api/v4/projects?topic=ai&order_by=last_activity_at&sort=desc&per_page=%d" % limit
    )
    return [
        {"src": "GitLab", "title": p.get("path_with_namespace", "?"),
         "info": (p.get("description") or "")[:120],
         "url": p.get("web_url", "")}
        for p in data
    ]


def _rss(name: str, url: str, limit: int = 4) -> list[dict]:
    r = requests.get(url, headers=_UA, timeout=_TIMEOUT)
    r.raise_for_status()
    root = ET.fromstring(r.content)
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if title:
            out.append({"src": name, "title": title, "info": "", "url": link})
        if len(out) >= limit:
            break
    if not out:  # Atom formatı (entry/title/link@href)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//a:entry", ns)[:limit]:
            title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
            link_el = entry.find("a:link", ns)
            link = link_el.get("href") if link_el is not None else ""
            if title:
                out.append({"src": name, "title": title, "info": "", "url": link})
    return out


def _collect_from(jobs) -> tuple[list[dict], list[str]]:
    items: list[dict] = []
    failures: list[str] = []
    for name, fn in jobs:
        try:
            items.extend(fn())
        except Exception as exc:  # noqa: BLE001 — mənbə xətası radarı dayandırmır
            failures.append("%s: %s" % (name, str(exc)[:80]))
    return items, failures


def collect() -> tuple[list[dict], list[str]]:
    """Həftəlik brif üçün BÜTÜN mənbələr."""
    jobs = [
        ("HuggingFace trending", _hf_models),
        ("HuggingFace papers", _hf_papers),
        ("GitHub", _github_new),
        ("GitLab", _gitlab_new),
    ]
    jobs += [("TG @%s" % ch, (lambda c=ch: _telegram_channel(c))) for ch in _TG_CHANNELS]
    jobs += [(name, (lambda n=name, u=url: _rss(n, u))) for name, url in _RSS_FEEDS]
    return _collect_from(jobs)


def collect_fast() -> tuple[list[dict], list[str]]:
    """Gündəlik nəbz üçün SÜRƏTLİ mənbələr (kanallar + trending)."""
    jobs = [("TG @%s" % ch, (lambda c=ch: _telegram_channel(c, limit=8))) for ch in _TG_CHANNELS]
    jobs.append(("HuggingFace trending", lambda: _hf_models(6)))
    return _collect_from(jobs)


def digest(items: list[dict], failures: list[str]) -> tuple[str, str]:
    """Xam siqnalları pulsuz LLM ilə həzm edib AZ brif qaytarır: (brif, model)."""
    import llm_router

    system = (
        "Sən RAMIN OS-in AI Radar analitikisən. Vendor-agnostik düşün: Google, OpenAI, "
        "açıq mənbə — hamısı bərabər namizəddir. Aşağıda son həftənin xam siqnalları var "
        "(model adları, repo adları, blog başlıqları, kanal mesajları). İşin:\n"
        "1) Marketinq OS-imiz üçün ƏN ƏHƏMİYYƏTLİ 5-6 yeniliyi seç (şəkil/video/səs/agent xəttləri).\n"
        "2) Hər seçim üçün DÜZ BU FORMATDA yaz:\n"
        "• <ad> — <1 cümlə nə olduğu>\n"
        "  Bizə: <konkret fayda və ya 'birbaşa faydası yoxdur'>\n"
        "  Pulsuz yol: <var/yox/qismən — bildiyin qədər, uydurma>\n"
        "  Orqan: <bu orqanlardan hansına taxılır: " + _ORGANS + ">\n"
        "3) Yalnız real ehtiyac görsən sonda 'TƏKLİF:' sətri ilə yeni modul/skill təklif et.\n"
        "QAYDALAR: yalnız verilən siqnallardan danış, ad uydurma, rəqəm uydurma. "
        "Hugging Face-dəki açıq modellər defolt PULSUZDUR (yerli işə salma və ya pulsuz inference) — "
        "onlara 'Pulsuz yol: yox' yazma. 'Bizə:' sətrində ümumi sözlər ('kömək edə bilər') qadağandır — "
        "konkret marketinq işinə bağla (post vizualı, reels, AZ səsləndirmə, rəqib analizi və s.). "
        "Bilmədiyini 'yoxlamaq lazımdır' kimi işarələ. Dil: Azərbaycan dili, sakit və konkret."
    )
    payload = json.dumps(items, ensure_ascii=False)
    # The weekly brief IS a synthesis/judgement task — the brain, not grunt work —
    # so it runs on the smart tier, which prefers the Claude subscription
    # (llm_router._claude_first). The strong anti-generic prompt below only pays off
    # on a strong model; the free floor still catches a capped account.
    text, model = llm_router.complete(
        payload, system=system, tier="smart", temperature=0.3, max_tokens=1200
    )
    header = "📡 AI RADAR — həftəlik brif (%s)\nSiqnal: %d mənbə qeydi | Həzm: %s\n" % (
        _dt.date.today().isoformat(), len(items), model
    )
    if failures:
        header += "ƏLÇATMAZ mənbələr: " + "; ".join(failures) + "\n"
    return header + "\n" + text.strip(), model


def _read_date(path: Path) -> _dt.date | None:
    try:
        return _dt.date.fromisoformat(path.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _write_today(path: Path) -> None:
    _RADAR_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(_dt.date.today().isoformat(), encoding="utf-8")


def _bootstrap_env() -> None:
    try:
        from ._bootstrap import load_env
        load_env()
    except Exception:
        pass


def _send_owner(text: str) -> None:
    try:
        from . import telegram
        owner = (os.getenv("TELEGRAM_OWNER_CHAT_ID") or os.getenv("GATEWAY_OWNER_ID") or "").strip()
        if owner and telegram.is_configured():
            telegram.send_message(owner, text)
        else:
            print("[radar] Telegram göndərilmədi: owner/token yoxdur")
    except Exception as exc:  # noqa: BLE001 — çatdırılma xətası hesabatı itirmir
        print("[radar] Telegram xətası: %s" % exc)


def _remember(title: str, body: str, tags: list[str]) -> None:
    try:
        from brain import remember as _brain_remember
        _brain_remember(title, body[:2500], type="lesson", tags=tags, source="ai-radar")
    except Exception as exc:  # noqa: BLE001
        print("[radar] brain qeydi yazıla bilmədi: %s" % exc)


def _save_outputs(brief: str) -> Path:
    _RADAR_DIR.mkdir(parents=True, exist_ok=True)
    report = _RADAR_DIR / (_dt.date.today().isoformat() + ".md")
    report.write_text(brief, encoding="utf-8")
    try:  # capabilities.md-yə əlavə — imkan xəritəsi radarla nəfəs alır
        with _CAPABILITIES.open("a", encoding="utf-8") as fh:
            fh.write("\n\n---\n\n## 📡 Radar qeydi — %s\n\n%s\n" % (
                _dt.date.today().isoformat(), brief))
    except Exception as exc:  # noqa: BLE001
        print("[radar] capabilities.md yazıla bilmədi: %s" % exc)
    # Brain korpusuna damcılat: EXISTING recall yolu lab tapıntılarını hər yeni
    # tapşırıqda avtomatik xatırladır — "siqnal gələn kimi lab-a bax" halqası.
    _remember("Radar brifi %s — həftənin AI mənzərəsi" % _dt.date.today().isoformat(),
              brief, ["radar", "landscape"])
    return report


def run(force: bool = False, send: bool = False) -> str:
    """HƏFTƏLİK dərin brif. Schedule hər gün çağırsa da taktı özü qoruyur."""
    _bootstrap_env()
    last = _read_date(_LAST_RUN)
    if not force and last is not None and (_dt.date.today() - last).days < 6:
        return "_[radar]_ növbə deyil (son brifdən %d gün keçib, takt: həftəlik)" % (
            (_dt.date.today() - last).days)

    items, failures = collect()
    if not items:
        return "_[radar]_ heç bir mənbədən siqnal alınmadı: " + "; ".join(failures)

    brief, _model = digest(items, failures)
    report = _save_outputs(brief)
    _write_today(_LAST_RUN)
    if send:
        _send_owner(brief)
    return brief + "\n\n(hesabat: %s)" % report


def pulse(force: bool = False, send: bool = False) -> str:
    """GÜNDƏLİK yüngül nəbz: sistem hər şeyi görür, sahib yalnız KRİTİK olanda
    narahat edilir. Sakit gündə cavab qısadır və heç nə göndərilmir."""
    _bootstrap_env()
    last = _read_date(_LAST_PULSE)
    if not force and last == _dt.date.today():
        return "_[radar-nəbz]_ bu gün artıq yoxlanılıb"

    items, failures = collect_fast()
    if not items:
        return "_[radar-nəbz]_ sürətli mənbələrdən siqnal alınmadı: " + "; ".join(failures)

    import llm_router
    system = (
        "Sən RAMIN OS-in növbətçi radar operatorusan. Qayda: sistem hər şeyi bilir, "
        "sahib yalnız GERÇƏKDƏN KRİTİK olanda narahat edilir. Aşağıda son saatların "
        "xam siqnalları var. KRİTİK sayılır (MAKSIMUM 3 seç):\n"
        "- böyük labdan YENİ FLAQMAN MODEL buraxılışı (məs. GPT-X, Gemini-X, Claude-X, "
        "yeni şəkil/video/səs flaqmanı) — bu HƏMİŞƏ kritikdir;\n"
        "- istifadə etdiyimiz API-lərdə breaking change və ya böyük qiymət dəyişikliyi;\n"
        "- sənayeni sarsıdan / çox səs-küylü hadisə;\n"
        "- marketinq OS-imizə birbaşa təsirli yenilik.\n"
        "KRİTİK DEYİL: adi məhsul xəbərləri, filmlər/əyləncə, ümumi tədqiqat xəbərləri.\n"
        "Belə xəbər yoxdursa, cavabın DÜZ bu olsun: NO_ALERT\n"
        "Varsa, hər biri üçün 2 sətir yaz: nə baş verib + bizə konkret təsiri. "
        "Uydurma qadağandır, yalnız verilən siqnallardan danış. Dil: Azərbaycan dili."
    )
    # Deciding what counts as CRITICAL is a judgement call -> smart tier (Claude).
    text, model = llm_router.complete(
        json.dumps(items, ensure_ascii=False), system=system,
        tier="smart", temperature=0.2, max_tokens=400,
    )
    _write_today(_LAST_PULSE)

    if "NO_ALERT" in text.upper():
        return "_[radar-nəbz]_ sakit gün (%d siqnal baxıldı, kritik yoxdur; həzm: %s)" % (
            len(items), model)

    alert = "🚨 RADAR XƏBƏRDARLIĞI (%s)\n\n%s" % (_dt.date.today().isoformat(), text.strip())
    if failures:
        alert += "\n\nƏLÇATMAZ mənbələr: " + "; ".join(failures)
    _remember("Radar xəbərdarlığı %s" % _dt.date.today().isoformat(), alert, ["radar", "alert"])
    if send:
        _send_owner(alert)
    return alert


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    force = "--force" in args
    send = "--send" in args
    if "--pulse" in args:
        print(pulse(force=force, send=send))
    else:
        print(run(force=force, send=send))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
