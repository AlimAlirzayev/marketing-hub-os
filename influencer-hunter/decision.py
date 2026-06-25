"""Decision framing for Influencer Hunter results.

Scoring answers "how strong is the evidence?". Decision framing answers the
human question: "what should we do with this shortlist?".
"""

from __future__ import annotations

from models import CampaignBrief, HuntResult, InfluencerCandidate


def score_band(score: float) -> str:
    if score >= 8:
        return "güclü"
    if score >= 6.5:
        return "perspektivli"
    if score >= 5:
        return "əl ilə yoxlanmalıdır"
    return "zəif"


def candidate_role(index: int, c: InfluencerCandidate) -> str:
    if index == 0:
        return "İlk əlaqə"
    if index == 1:
        return "İkinci seçim"
    if index == 2:
        return "Üçüncü seçim"
    return "Ehtiyat namizəd"


def proof_points(c: InfluencerCandidate) -> list[str]:
    points: list[str] = []
    if c.audience_fit >= 7:
        points.append("auditoriya və mövzu uyğunluğu güclüdür")
    elif c.audience_fit >= 5:
        points.append("auditoriya uyğunluğu var, amma əl ilə yoxlanmalıdır")
    if c.content_fit >= 7:
        points.append("son kontent Reels/video hekayəçilik üçün uyğundur")
    elif c.content_fit >= 5:
        points.append("kontent brief ilə qismən uyğun gəlir")
    if c.engagement_quality >= 7:
        points.append("engagement keyfiyyəti gözləniləndən yaxşıdır")
    elif c.engagement_quality <= 4:
        points.append("engagement zəif görünür")
    if c.feedback_sentiment >= 6.5:
        points.append("izləyici reaksiyası əsasən müsbətdir")
    elif c.feedback_sentiment <= 4:
        points.append("rəy sentimenti əl ilə yoxlanmalıdır")
    if c.brand_safety >= 8:
        points.append("toplanan sübutlarda brend təhlükəsizliyi riski aşağıdır")
    elif c.brand_safety <= 6:
        points.append("əlaqədən əvvəl brend təhlükəsizliyi yoxlanmalıdır")
    if c.proof_density >= 6:
        points.append("əlaqədən əvvəl baxmaq üçün kifayət qədər sübut var")
    elif c.proof_density < 3:
        points.append("sübut azdır; final seçim yox, lead kimi saxlanmalıdır")
    return list(dict.fromkeys(points))[:5]


def next_checks(c: InfluencerCandidate) -> list[str]:
    checks = [
        "Qiymət siyahısı, istifadə hüquqları və eksklüzivlik şərtlərini soruşun.",
        "Son 30 gün Reels insight-larını istəyin: reach, izləmə müddəti, save, share və auditoriya şəhərləri.",
        "Namizədi təsdiqləməzdən əvvəl linkdəki Reels/postlara əl ilə baxın.",
    ]
    if c.brand_safety < 8 or c.flags:
        checks.insert(0, "Əlaqədən əvvəl brend təhlükəsizliyi və authenticity qeydlərini yoxlayın.")
    if c.proof_density < 5:
        checks.insert(0, "Təsdiqli tövsiyə saymazdan əvvəl daha çox son Reels və rəy toplayın.")
    return checks[:4]


def candidate_decision(c: InfluencerCandidate, index: int) -> dict:
    points = proof_points(c)
    return {
        "role": candidate_role(index, c),
        "score_band": score_band(c.total_score),
        "decision": (
            f"Bu kampaniya üçün {candidate_role(index, c).lower()}"
            if c.total_score >= 6.5
            else "Hələ təsdiqli creator deyil, araşdırma lead-i kimi saxlayın"
        ),
        "why": points or ["inamlı tövsiyə üçün sübut hələ zəifdir"],
        "next_checks": next_checks(c),
    }


def _confidence(shortlist: list[InfluencerCandidate]) -> tuple[str, str]:
    if not shortlist:
        return "aşağı", "Mövcud sübutlardan shortlist çıxmadı."
    avg = sum(c.total_score for c in shortlist) / len(shortlist)
    proof = sum(c.proof_density for c in shortlist) / len(shortlist)
    if avg >= 7.5 and proof >= 5.5:
        return "yüksək", "Top namizədlərdə həm skor, həm də baxıla bilən sübut güclüdür."
    if avg >= 6 and proof >= 3:
        return "orta", "Seçim siyahısı ilk əlaqə üçün yararlıdır, amma bəzi sübutlar əl ilə yoxlanmalıdır."
    return "aşağı", "Daha çox sübut toplanana qədər nəticələr lead kimi qəbul edilməlidir."


def result_decision(res: HuntResult) -> dict:
    b: CampaignBrief = res.brief
    confidence, reason = _confidence(res.shortlist)
    if res.shortlist:
        first = res.shortlist[0]
        answer = (
            f"@{first.handle} ilə başlayın. Bu seçim siyahısı {b.brand or 'brend'} üçün "
            f"{b.product or 'kampaniya məhsulu'} mövzusunda {b.content_format} kontenti "
            "canlandıra bilən və aktiv seçim filterlərindən keçən influencer/blogger namizədlərini göstərir."
        )
    elif res.candidates:
        answer = (
            "Skan mümkün namizədlər tapdı, amma heç biri hələ final tövsiyə səviyyəsində deyil. "
            "Daha dəqiq analiz üçün seed profil əlavə edin və ya filterləri yumşaldın."
        )
    else:
        answer = (
            "Hazırki sübutlarla tövsiyə ediləcək namizəd yoxdur. Canlı Instagram datasını aktiv edin "
            "və ya analiz üçün seed profil əlavə edin."
        )
    blockers = []
    if not res.shortlist:
        blockers.append("Hələ təsdiqli seçim siyahısı yoxdur.")
    if any(s.status == "skipped" and "APIFY_API_TOKEN" in s.note for s in res.source_status):
        blockers.append("Apify aktiv deyil və ya quraşdırılmayıb, canlı Instagram sübutu yoxdur.")
    if any(c.proof_density < 4 for c in res.shortlist):
        blockers.append("Bəzi seçim siyahısı namizədlərində sübut sıxlığı zəifdir.")
    if res.filtered_out:
        blockers.append(f"{len(res.filtered_out)} hesab aktiv filterlərə görə kənarda qaldı.")
    gates = []
    if res.filters.require_local_market:
        gates.append("Azərbaycan/local auditoriya siqnalı")
    if res.filters.require_human_creator:
        gates.append("fərdi influencer/blogger")
    if res.filters.require_campaign_fit:
        gates.append("kampaniya-fit sübutu")
    if res.filters.min_recommendation_score:
        gates.append(f"minimum tövsiyə balı: {res.filters.min_recommendation_score:.1f}+")
    if res.filters.min_followers:
        gates.append(f"minimum izləyici: {res.filters.min_followers:,}+")
    gate = " · ".join(gates) if gates else "aktiv seçim filteri yoxdur"
    return {
        "purpose": "Bu konkret kampaniya brief-i üçün ilk kimə yazacağımızı seçmək.",
        "campaign_question": (
            f"{b.brand or 'brend'} / {b.product or 'məhsul'} üçün emosional "
            f"{b.content_format} kontentini kim daha inandırıcı canlandıra bilər?"
        ),
        "active_gate": gate,
        "answer": answer,
        "confidence": confidence,
        "confidence_reason": reason,
        "what_was_ranked": [
            gate,
            "kampaniya auditoriyası və mövzu uyğunluğu",
            "tapşırığa uyğun Reels/post sübutları",
            "təkcə izləyici sayı yox, engagement keyfiyyəti",
            "izləyici rəylərinin sentimenti",
            "brend təhlükəsizliyi və authenticity riski",
            "əl ilə baxıla bilən sübutların miqdarı",
        ],
        "blockers": blockers,
        "recommended_next_step": (
            "Linkdəki sübutlara baxın, top 1-2 namizədi seçin, sonra qiymət və Reels insight-larını istəyin."
            if res.shortlist else
            "5-10 yerli travel/lifestyle profil əlavə edin və ya Apify-ni aktiv edib skanı yenidən başladın."
        ),
    }
