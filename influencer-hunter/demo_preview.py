"""Standalone DEMO preview generator for Influencer Hunter.

Apify's free $5/month budget is exhausted (resets ~5 July), so a live scan
cannot run. This tool feeds clearly-synthetic creators through the REAL pipeline
(score -> ai_eval LLM -> eligibility filters -> decision framing -> API payload)
and bakes the result into a single self-contained HTML file that reuses the live
frontend. Every screen is marked DEMO; no synthetic number is presented as real.

Run:  .venv/Scripts/python.exe demo_preview.py
"""

from __future__ import annotations

import json
import os

import ai_eval
import decision
import filters as filters_mod
import resolve as resolve_mod
import score as score_mod
import server
from models import EvidenceItem, HuntResult, InfluencerCandidate, SelectionFilters, SourceStatus

BASE = os.path.dirname(os.path.abspath(__file__))

QUERY = (
    "Xalq Sigorta üçün səyahət sığortası barədə emosional Instagram Reel ssenarisini "
    "canlandıracaq Azərbaycanlı travel/lifestyle influencer lazımdır."
)


def _ev(kind, text, likes=0, comments=0, views=0, url="", is_comment=False):
    metrics = {"is_comment": True} if is_comment else {"likes": likes, "comments": comments, "video_views": views}
    return EvidenceItem(kind=kind, url=url, text=text, metrics=metrics)


def _demo_candidates() -> list[InfluencerCandidate]:
    """Fictional creators (demo_* handles) covering every pipeline outcome:
    strong shortlist, reserve, off-topic, corporate, and foreign-market."""
    return [
        InfluencerCandidate(
            handle="demo_aytac_travels", name="Aytac (DEMO) · Səyahət bloggeri",
            bio="Bakı əsaslı travel blogger. Gürcüstan, Türkiyə, ailə səyahətləri və real təcrübələr.",
            followers=128_000, following=820, posts_count=640,
            categories=["Travel", "Lifestyle"],
            evidence=[
                _ev("reel", "Gürcüstana uçmadan əvvəl mütləq səyahət sığortası edin — baqaj itdi, xəstələndik, sığorta hər şeyi qarşıladı. Real hekayə.", 5400, 260, 92_000, "https://www.instagram.com/reel/DEMOaytac1/"),
                _ev("reel", "Ailəcən tətil: uçuş gecikdi, sığorta sayəsində oteldə qaldıq. Bu vacib məqamı izah edirəm.", 4100, 190, 71_000, "https://www.instagram.com/reel/DEMOaytac2/"),
                _ev("comment", "Çox faydalı oldu, təşəkkürlər! Real təcrübədir, məsləhətə görə sığorta etdim.", is_comment=True),
                _ev("comment", "Əla izah etdin, bunu bilmirdim. Gələn səfərə hökmən edəcəm.", is_comment=True),
            ],
        ),
        InfluencerCandidate(
            handle="demo_familytrip_az", name="Nigar (DEMO) · Ailə & Səyahət",
            bio="Azərbaycanlı ana. Uşaqlarla səyahət, təhlükəsizlik və rahatlıq. Bakı.",
            followers=64_500, following=410, posts_count=380,
            categories=["Family", "Travel"],
            evidence=[
                _ev("reel", "Uşaqlarla xaricə çıxarkən sığorta niyə vacibdir — qızım xəstələndi, klinika bahalı idi, sığorta ödədi.", 2600, 140, 48_000, "https://www.instagram.com/reel/DEMOfam1/"),
                _ev("post", "Səyahət çantası check-list: pasport, viza, sığorta polisi, dərmanlar.", 1800, 60, 0, "https://www.instagram.com/p/DEMOfam2/"),
                _ev("comment", "Çox doğru deyirsən, güvən və rahatlıq üçün vacibdir.", is_comment=True),
            ],
        ),
        InfluencerCandidate(
            handle="demo_kamran_explores", name="Kamran (DEMO) · Macəra",
            bio="Adventure & travel creator from Baku. Dağlar, dənizlər, yeni ölkələr.",
            followers=212_000, following=300, posts_count=910,
            categories=["Travel", "Adventure"],
            evidence=[
                _ev("reel", "Solo səyahətdə baqajım itdi — sığorta olmadan necə əziyyət çəkdiyimi danışıram.", 9800, 410, 180_000, "https://www.instagram.com/reel/DEMOkam1/"),
                _ev("reel", "Ən gözəl 5 ölkə və hər birində niyə sığorta etdim.", 7200, 230, 140_000, "https://www.instagram.com/reel/DEMOkam2/"),
                _ev("comment", "Möhtəşəm kontentdir, real və dürüst.", is_comment=True),
            ],
        ),
        InfluencerCandidate(
            handle="demo_foodbaku", name="Bakı Yeməkləri (DEMO)",
            bio="Bakının ən dadlı restoranları və reseptləri. Food blogger.",
            followers=98_000, following=120, posts_count=1200,
            categories=["Food"],
            evidence=[
                _ev("reel", "Bakıda ən yaxşı kababçılar — top 5 ünvan!", 3200, 90, 60_000, "https://www.instagram.com/reel/DEMOfood1/"),
                _ev("post", "Ev şəraitində plov resepti.", 2100, 40, 0, "https://www.instagram.com/p/DEMOfood2/"),
            ],
        ),
        InfluencerCandidate(
            handle="demo_some_insurance", name="DEMO Sığorta Şirkəti",
            bio="Official insurance company account. Sığorta məhsulları və xidmətlər.",
            followers=41_000, following=15, posts_count=300,
            categories=["Company"],
            evidence=[_ev("post", "Yeni səyahət sığortası məhsulumuz.", 120, 4, 0, "https://www.instagram.com/p/DEMOins1/")],
        ),
        InfluencerCandidate(
            handle="demo_india_traveler", name="DEMO Traveler",
            bio="Travel creator from India. Exploring the world, based in Mumbai.",
            followers=156_000, following=500, posts_count=700,
            categories=["Travel"],
            evidence=[_ev("reel", "My trip to Dubai and Maldives — travel tips!", 4000, 100, 80_000, "https://www.instagram.com/reel/DEMOind1/")],
        ),
    ]


def build_payload() -> dict:
    brief = resolve_mod.resolve(QUERY)
    candidates = _demo_candidates()
    ranked = score_mod.score_candidates(candidates, brief)
    ranked = ai_eval.apply_ai_evaluation(brief, ranked)
    selection = SelectionFilters(min_followers=20_000, min_score=0.0)
    eligible, filtered_out = filters_mod.apply_eligibility(ranked, selection)
    min_pick = max(selection.min_score, selection.min_recommendation_score)
    picks = score_mod.shortlist(eligible, n=3, min_score=min_pick)

    statuses = [
        SourceStatus("DEMO", "ok", "Sintetik namizədlər real pipeline-dan keçirildi (canlı Apify deyil)"),
        SourceStatus("apify (canlı)", "skipped", "Pulsuz $5/ay limiti dolub (5.09/5); sıfırlanma ~5 İyul 2026"),
    ]
    res = HuntResult(
        query=QUERY, brief=brief, filters=selection,
        candidates=eligible, filtered_out=filtered_out, shortlist=picks,
        verdict="", source_status=statuses, total_seen=len(candidates), rejected=0,
    )
    # real verdict (LLM) on the demo shortlist, so the AZ-output fix is visible
    try:
        import hunt as hunt_mod
        res.verdict = hunt_mod._verdict(brief, picks)
    except Exception:
        res.verdict = ""
    return server._payload(res)


_BANNER = (
    '<div style="background:#7a1115;color:#fff;text-align:center;padding:9px 14px;'
    'font:700 13px/1.4 -apple-system,Segoe UI,Arial;letter-spacing:.03em">'
    '⚠ DEMO ÖNİZLƏMƏ — sintetik (demo_*) namizədlər real pipeline-dan keçib. '
    'Canlı Instagram datası deyil: Apify pulsuz $5/ay limiti dolub, ~5 İyul 2026-da sıfırlanır.'
    '</div>'
)


def main() -> None:
    payload = build_payload()
    with open(os.path.join(BASE, "static", "index.html"), encoding="utf-8") as f:
        html = f.read()

    inject = (
        "<script>\n"
        f"const DEMO_PAYLOAD = {json.dumps(payload, ensure_ascii=False)};\n"
        "document.body.insertAdjacentHTML('afterbegin', " + json.dumps(_BANNER) + ");\n"
        "window.fetch = async () => ({ json: async () => ({}) });\n"  # neutralise health() call
        "document.getElementById('engtxt').textContent = 'DEMO rejimi · canlı backend qoşulu deyil';\n"
        "render(DEMO_PAYLOAD);\n"
        "</script>\n"
    )
    html = html.replace("health();\n</script>", "/* health() skipped in demo */\n</script>")
    html = html.replace("</body>", inject + "</body>")

    out_dir = os.path.join(BASE, "data", "reports")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "DEMO-preview.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("shortlist:", [c["handle"] for c in payload["shortlist"]])
    print("filtered_out:", [(c["handle"], (c["flags"] or ["-"])[0]) for c in payload["filtered_out"]])
    print("preview written:", out)


if __name__ == "__main__":
    main()
