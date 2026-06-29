"""Pure logic tests for Influencer Hunter."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analyze  # noqa: E402
import config  # noqa: E402
import resolve  # noqa: E402
import score  # noqa: E402
import sources  # noqa: E402
import sources_rapidapi  # noqa: E402
import sources_youtube  # noqa: E402
import decision  # noqa: E402
import filters  # noqa: E402
from models import EvidenceItem, HuntResult, InfluencerCandidate, SelectionFilters  # noqa: E402


def _brief():
    return resolve._fallback(
        "Xalq Sigorta üçün səyahət sığortası barədə emosional Instagram Reel canlandıracaq travel blogger lazımdır"
    )


def test_fallback_extracts_travel_insurance_brief():
    b = _brief()
    assert b.brand == "Xalq Sigorta"
    assert "səyahət" in b.product
    assert "travelbloggeraz" in b.hashtags
    assert "travelblogger" not in b.hashtags
    assert "sigorta" not in b.hashtags
    assert "travel blogger" in b.creator_archetypes


def test_scoring_prefers_relevant_safe_reel_creator():
    b = _brief()
    relevant = InfluencerCandidate(
        handle="realtravelaz",
        name="Real Travel AZ",
        bio="Baku based travel blogger. Gürcüstan, airport, otel və ailə səyahətləri.",
        followers=60_000,
        evidence=[
            EvidenceItem(
                kind="reel",
                url="https://instagram.com/reel/abc/",
                text="Gürcüstan səyahətindən əvvəl riskləri düşünün: baqaj, uçuş, ailə və sığorta vacibdir.",
                metrics={"likes": 3600, "comments": 180, "video_views": 70_000},
            ),
            EvidenceItem(kind="comment", text="Çox faydalı oldu, təşəkkürlər, real təcrübədir.", metrics={"is_comment": True}),
            EvidenceItem(kind="comment", text="Əla izah etdin, bunu bilmirdim.", metrics={"is_comment": True}),
        ],
    )
    weak = InfluencerCandidate(
        handle="megafollow",
        name="Mega Follow",
        bio="Luxury lifestyle giveaways",
        followers=850_000,
        evidence=[
            EvidenceItem(
                kind="post",
                url="https://instagram.com/p/xyz/",
                text="Giveaway, like, follow, tag friends.",
                metrics={"likes": 1200, "comments": 3, "video_views": 0},
            ),
            EvidenceItem(kind="comment", text="fake spam reklam", metrics={"is_comment": True}),
        ],
    )
    ranked = score.score_candidates([weak, relevant], b)
    assert ranked[0].handle == "realtravelaz"
    assert ranked[0].total_score > ranked[1].total_score
    assert ranked[0].content_fit >= 7
    assert ranked[0].feedback_sentiment > 5


def test_brand_safety_penalizes_risky_creator():
    b = _brief()
    risky = InfluencerCandidate(
        handle="riskypromo",
        bio="casino bet merc promos",
        followers=40_000,
        evidence=[
            EvidenceItem(kind="reel", text="Casino bet promo and travel giveaway", metrics={"likes": 1000, "comments": 50, "video_views": 20_000})
        ],
    )
    score.score_candidates([risky], b)
    assert risky.brand_safety < 7
    assert any("riskli" in f for f in risky.flags)


def test_source_parsers_normalize_handles_and_metrics():
    assert sources._handle("https://www.instagram.com/Real.Travel_AZ/?x=1") == "real.travel_az"
    assert sources._as_int("12.5k") == 12500
    ev = sources._post_evidence(
        {
            "ownerUsername": "realtravelaz",
            "caption": "Travel reel",
            "shortCode": "ABC",
            "likesCount": "1,200",
            "commentsCount": 44,
            "videoViewCount": "33k",
        },
        "realtravelaz",
    )
    assert ev.kind == "reel"
    assert ev.metrics["likes"] == 1200
    assert ev.metrics["video_views"] == 33000


def test_decision_frame_explains_result_purpose():
    b = _brief()
    res = HuntResult(query=b.query, brief=b, candidates=[], shortlist=[])
    frame = decision.result_decision(res)
    assert "ilk kimə yazacağımızı" in frame["purpose"]
    assert frame["confidence"] == "aşağı"
    assert "namizəd yoxdur" in frame["answer"]


def test_candidate_decision_has_action_language():
    b = _brief()
    c = InfluencerCandidate(
        handle="realtravelaz",
        bio="Baku travel blogger",
        followers=20_000,
        evidence=[
            EvidenceItem(kind="reel", url="https://instagram.com/reel/a", text="travel sigorta risk story", metrics={"likes": 1200, "comments": 80, "video_views": 30_000}),
            EvidenceItem(kind="comment", text="çox faydalı və real", metrics={"is_comment": True}),
        ],
    )
    score.score_candidates([c], b)
    cd = decision.candidate_decision(c, 0)
    assert cd["role"] == "İlk əlaqə"
    assert cd["why"]
    assert cd["next_checks"]
    # sentiment_to_emoji is wired into the decision payload (was an orphan helper)
    assert cd["sentiment_emoji"] in {"😊", "🙂", "😐", "😞"}
    assert cd["sentiment_emoji"] == decision.sentiment_to_emoji(c.feedback_sentiment)


def test_sentiment_to_emoji_bands():
    assert decision.sentiment_to_emoji(9.0) == "😊"
    assert decision.sentiment_to_emoji(6.5) == "🙂"
    assert decision.sentiment_to_emoji(5.0) == "😐"
    assert decision.sentiment_to_emoji(2.0) == "😞"


def test_min_followers_gate_excludes_small_accounts():
    big = InfluencerCandidate(handle="bigcreatoraz", bio="Baku content creator", followers=25_000, total_score=8)
    small = InfluencerCandidate(handle="smallcreatoraz", bio="Baku content creator", followers=19_999, total_score=9)
    unknown = InfluencerCandidate(handle="unknowncreatoraz", bio="Baku content creator", followers=None, total_score=9)
    eligible, filtered_out = filters.apply_eligibility(
        [small, big, unknown],
        SelectionFilters(min_followers=20_000, min_score=0, allow_unknown_followers=False, require_campaign_fit=False),
    )
    assert [c.handle for c in eligible] == ["bigcreatoraz"]
    assert {c.handle for c in filtered_out} == {"smallcreatoraz", "unknowncreatoraz"}
    assert any("minimum izləyici" in f for f in small.flags)
    assert any("izləyici sayı görünmür" in f for f in unknown.flags)


def test_creator_gate_excludes_brands_and_competitors():
    creator = InfluencerCandidate(
        handle="aritravelblog",
        name="Arifa Eminli | Yemek Seyahat Viza Kitab Reklam",
        bio="Azerbaijani travel blogger",
        followers=108_000,
        total_score=8,
    )
    competitor = InfluencerCandidate(
        handle="ateshgah_insurance",
        name="Ateshgah Sigorta",
        bio="Insurance company official account",
        followers=20_980,
        total_score=9,
    )
    airline = InfluencerCandidate(
        handle="azerbaijanairlines",
        name="AZAL - Azerbaijan Airlines",
        bio="Official airline account",
        followers=368_000,
        total_score=9,
    )
    aggregator = InfluencerCandidate(
        handle="azerbaijanplaces",
        name="Azerbaijan Places",
        bio="Best places and travel guide",
        followers=1_443_323,
        total_score=9,
        evidence=[
            EvidenceItem(kind="reel", text="#travelblogger #travel #azerbaijan"),
        ],
    )
    foreign_creator = InfluencerCandidate(
        handle="heen.akhan1230",
        name="HEENA KHAN",
        bio="From India reel creator",
        followers=45_145,
        total_score=9,
    )
    eligible, filtered_out = filters.apply_eligibility(
        [competitor, airline, aggregator, foreign_creator, creator],
        SelectionFilters(min_followers=20_000, require_campaign_fit=False),
    )
    assert [c.handle for c in eligible] == ["aritravelblog"]
    assert {c.handle for c in filtered_out} == {
        "ateshgah_insurance",
        "azerbaijanairlines",
        "azerbaijanplaces",
        "heen.akhan1230",
    }
    assert any("rəqib" in f for f in competitor.flags)
    assert any("korporativ" in f for f in airline.flags)
    assert any("influencer/blogger" in f for f in aggregator.flags)
    assert any("Azərbaycan/local" in f for f in foreign_creator.flags)


def test_local_market_gate_uses_identity_and_language_signals():
    local_by_city = InfluencerCandidate(
        handle="fiadaline_",
        name="Fidan Rasulova",
        bio="Baku, Azerbaijan content creator lifestyle blogger",
        followers=52_889,
        total_score=8,
    )
    local_by_language = InfluencerCandidate(
        handle="realcreator",
        name="Real Creator",
        bio="Travel blogger",
        followers=35_000,
        total_score=8,
        evidence=[EvidenceItem(kind="reel", text="Səyahət zamanı rahatlıq və güvən çox vacibdir.")],
    )
    foreign = InfluencerCandidate(
        handle="shabi.me",
        name="Şebnem",
        bio="Part time social media influencer, UGC lifestyle, Türkiye",
        followers=28_212,
        total_score=8,
    )
    foreign_with_az_language = InfluencerCandidate(
        handle="narminsun",
        name="Günəşin qızı",
        bio="Influencer, traveller in Simkent Kazakhstan",
        followers=92_387,
        total_score=8,
    )
    eligible, filtered_out = filters.apply_eligibility(
        [foreign, foreign_with_az_language, local_by_city, local_by_language],
        SelectionFilters(min_followers=20_000, require_campaign_fit=False),
    )
    assert {c.handle for c in eligible} == {"fiadaline_", "realcreator"}
    assert {c.handle for c in filtered_out} == {"shabi.me", "narminsun"}


def test_relevance_not_diluted_by_semantic_expansion():
    """A creator hitting several campaign terms should read as strongly relevant
    even when the brief expands to 60+ semantic keys."""
    b = _brief()
    c = InfluencerCandidate(
        handle="realtravelaz",
        name="Real Travel AZ",
        bio="Baku based travel blogger. Gürcüstan, airport, otel və ailə səyahətləri.",
        followers=60_000,
        evidence=[
            EvidenceItem(
                kind="reel",
                url="https://www.instagram.com/reel/abc/",
                text="Gürcüstan səyahətindən əvvəl riskləri düşünün: baqaj, uçuş, ailə və sığorta vacibdir.",
                metrics={"likes": 3600, "comments": 180, "video_views": 70_000},
            ),
        ],
    )
    score.score_candidates([c], b)
    assert c.content_fit >= 7
    assert c.audience_fit >= 6


def test_engagement_band_matches_follower_tier_benchmark():
    assert score.expected_engagement_rate(10_000) == 0.055
    assert score.expected_engagement_rate(60_000) == 0.04
    assert score.expected_engagement_rate(2_000_000) == 0.015
    assert score.engagement_band(60_000, 0.06) == "güclü"
    assert score.engagement_band(60_000, 0.035) == "normal"
    assert score.engagement_band(60_000, 0.005) == "zəif"
    assert score.engagement_band(None, 0.05) == "naməlum"


def test_post_url_prefers_permalink_never_cdn_image():
    # CDN image (displayUrl) must never become the post url
    assert sources._post_url({"displayUrl": "https://scontent.cdninstagram.com/x.jpg"}, "user") \
        == "https://www.instagram.com/user/"
    # shortcode builds a clean permalink
    assert sources._post_url({"shortCode": "XYZ", "videoViewCount": 10}, "u") \
        == "https://www.instagram.com/reel/XYZ/"
    # a real permalink is kept as-is
    assert sources._post_url({"url": "https://www.instagram.com/p/REAL1/"}, "u") \
        == "https://www.instagram.com/p/REAL1/"
    assert sources._is_post_permalink("https://www.instagram.com/reel/Ab-1/")
    assert not sources._is_post_permalink("https://www.instagram.com/yegish_blog/")
    assert not sources._is_post_permalink("https://scontent.cdninstagram.com/v/123.jpg")


def test_actor_cache_round_trip_and_expiry(tmp_path=None):
    import os as _os
    import time as _time
    import config
    config.ensure_dirs()
    actor, payload = "apify/test-actor", {"q": "az", "n": [1, 2]}
    sources._cache_write(actor, payload, [{"a": 1}])
    try:
        assert sources._cache_read(actor, payload) == [{"a": 1}]
        assert sources._cache_read(actor, {"q": "other"}) is None
        path = sources._cache_path(actor, payload)
        old = _time.time() - (config.CACHE_TTL + 5)
        _os.utime(path, (old, old))
        assert sources._cache_read(actor, payload) is None
    finally:
        try:
            _os.remove(sources._cache_path(actor, payload))
        except OSError:
            pass


def test_fallback_keeps_core_discovery_hashtags_after_breadth_expansion():
    b = _brief()
    assert "travelbloggeraz" in b.hashtags
    assert "travelblogger" not in b.hashtags
    assert "sigorta" not in b.hashtags
    assert len(b.hashtags) <= 10


def _fake_youtube_get(path, params):
    if path == "channels" and "forHandle" in params:
        return {"items": [{"id": "UC_a"}]}
    if path == "search":
        return {"items": [{"snippet": {"channelId": "UC_b"}}]}
    if path == "channels":
        items = []
        for cid in params["id"].split(","):
            items.append({
                "id": cid,
                "snippet": {"title": "Travel " + cid, "customUrl": cid.lower(),
                            "description": "Baku travel blogger sığorta", "country": "AZ",
                            "thumbnails": {"high": {"url": "http://img/" + cid}}},
                "statistics": {"subscriberCount": "120000", "videoCount": "500", "viewCount": "9000000"},
                "contentDetails": {"relatedPlaylists": {"uploads": "PL_" + cid}},
            })
        return {"items": items}
    if path == "playlistItems":
        return {"items": [{"contentDetails": {"videoId": params["playlistId"] + "_v1"}}]}
    if path == "videos":
        return {"items": [{"id": v, "snippet": {"title": "Səyahət sığorta", "description": "Gürcüstan baqaj"},
                           "statistics": {"likeCount": "4000", "commentCount": "150", "viewCount": "90000"}}
                          for v in params["id"].split(",")]}
    if path == "commentThreads":
        texts = ["Çox faydalı oldu, sığorta vacibdir", "Real təcrübədir təşəkkürlər", "wow", "wow", "wow"]
        return {"items": [{"snippet": {"topLevelComment": {"snippet": {
            "textDisplay": t, "authorDisplayName": "u", "likeCount": "2"}}}} for t in texts]}
    return {"items": []}


def test_orchestrate_resolve_platforms():
    import orchestrate
    assert orchestrate.resolve_platforms("youtube") == ["youtube"]
    assert set(orchestrate.resolve_platforms("all")) == set(orchestrate.platforms())
    assert {"instagram", "youtube", "web"} <= set(orchestrate.platforms())
    assert set(orchestrate.resolve_platforms("instagram,youtube")) == {"instagram", "youtube"}
    assert orchestrate.resolve_platforms("bogus") == ["instagram"]


def test_web_connector_extracts_named_creators_offline():
    import sources_web
    o_search, o_fetch, o_avail = sources_web._search, sources_web._fetch_text, sources_web.available
    o_json = sources_web.llm.complete_json
    sources_web._search = lambda q, limit=5: ["https://example.az/best-az-bloggers"]
    sources_web._fetch_text = lambda url: "Azərbaycanlı travel bloggerlər siyahısı: Aytac və Kamran."
    sources_web.available = lambda: True
    sources_web.llm.complete_json = lambda *a, **k: {"creators": [
        {"name": "Aytac", "handle": "@aytac_travels", "platform": "instagram", "note": "səyahət bloggeri"},
    ]}
    try:
        cands, statuses, seen = sources_web.collect(_brief())
        assert seen >= 1
        c = next(x for x in cands if x.handle == "aytac_travels")
        assert c.platform == "web"
        assert any(e.kind == "mention" for e in c.evidence)
    finally:
        sources_web._search, sources_web._fetch_text, sources_web.available = o_search, o_fetch, o_avail
        sources_web.llm.complete_json = o_json


def test_orchestrate_fanout_merges_platforms():
    import orchestrate
    import sources as sources_mod
    import sources_youtube as yt_mod
    from models import SourceStatus
    o_ig, o_yt = sources_mod.collect, yt_mod.collect
    o_tok, o_key = config.APIFY_API_TOKEN, config.YOUTUBE_API_KEY
    sources_mod.collect = lambda brief, **k: ([InfluencerCandidate(handle="iguser", platform="instagram", followers=30000)], [SourceStatus("ig", "ok", "")], 1)
    yt_mod.collect = lambda brief, **k: ([InfluencerCandidate(handle="ytuser", platform="youtube", followers=40000)], [SourceStatus("yt", "ok", "")], 1)
    config.APIFY_API_TOKEN, config.YOUTUBE_API_KEY = "x", "y"
    try:
        cands, statuses, seen = orchestrate.collect(_brief(), source="instagram,youtube")
        handles = {(c.platform, c.handle) for c in cands}
        assert ("instagram", "iguser") in handles
        assert ("youtube", "ytuser") in handles
        assert seen == 2
        assert any(s.source == "orkestrator" for s in statuses)
    finally:
        sources_mod.collect, yt_mod.collect = o_ig, o_yt
        config.APIFY_API_TOKEN, config.YOUTUBE_API_KEY = o_tok, o_key


def test_orchestrate_fallback_uses_secondary_when_primary_empty():
    import orchestrate
    from models import SourceStatus
    primary = orchestrate.Connector(
        "fake-primary", "fakeplat",
        lambda brief, **k: ([], [SourceStatus("fake-primary", "empty", "")], 0),
        lambda: True, cost="paid", priority=1)
    secondary = orchestrate.Connector(
        "fake-secondary", "fakeplat",
        lambda brief, **k: ([InfluencerCandidate(handle="got", platform="fakeplat")], [SourceStatus("fake-secondary", "ok", "")], 1),
        lambda: True, cost="free", priority=2)
    orchestrate.REGISTRY.extend([primary, secondary])
    try:
        cands, statuses, seen = orchestrate._run_platform("fakeplat", _brief(), None, True)
        assert [c.handle for c in cands] == ["got"]
        assert any(s.source == "fake-secondary" for s in statuses)
    finally:
        orchestrate.REGISTRY.remove(primary)
        orchestrate.REGISTRY.remove(secondary)


def test_orchestrate_merge_by_handle_dedupes_same_platform():
    import orchestrate
    a = InfluencerCandidate(handle="dup", platform="youtube", evidence=[EvidenceItem(kind="video", text="a")])
    b = InfluencerCandidate(handle="dup", platform="youtube", followers=5000, evidence=[EvidenceItem(kind="comment", text="b")])
    out = orchestrate._merge_by_handle([a, b])
    assert len(out) == 1
    assert len(out[0].evidence) == 2
    assert out[0].followers == 5000


_TG_HTML = (
    '<div class="tgme_channel_info_header_title"><span>AZ Travel Channel</span></div>'
    '<div class="tgme_channel_info_description">Azərbaycan səyahət kanalı, Bakı</div>'
    '<div class="tgme_channel_info_counter"><span class="counter_value">52.4K</span>'
    '<span class="counter_type">subscribers</span></div>'
    '<div class="tgme_widget_message_text">Gürcüstana səyahət, sığorta vacibdir</div>'
    '<div class="tgme_widget_message_footer"><span class="tgme_widget_message_views">12.5K</span></div>'
)


def test_telegram_parser_extracts_channel_and_posts():
    import sources_telegram as tg
    c = tg._parse_channel("az_travel_ch", _TG_HTML)
    assert c is not None
    assert c.platform == "telegram"
    assert c.followers == 52_400
    assert c.name == "AZ Travel Channel"
    posts = [e for e in c.evidence if e.kind == "post"]
    assert posts and posts[0].metrics["video_views"] == 12_500
    tg._merge_metrics(c)
    assert c.engagement_rate > 0  # views/subscribers reach ratio


def test_telegram_collect_uses_seed_and_skips_network():
    import sources_telegram as tg
    import sources_web
    o_scrape, o_search = tg._scrape_channel, sources_web._search
    tg._scrape_channel = lambda u: tg._parse_channel(u, _TG_HTML)
    sources_web._search = lambda q, limit=6: []  # no live discovery in test
    try:
        cands, statuses, seen = tg.collect(_brief(), seed_handles=["az_travel_ch"])
        assert any(c.platform == "telegram" and c.handle == "az_travel_ch" for c in cands)
    finally:
        tg._scrape_channel, sources_web._search = o_scrape, o_search


def test_country_signal_drives_local_market_gate():
    az = InfluencerCandidate(handle="az_creator", name="Yerli", bio="travel vlog", country="AZ", followers=50_000)
    foreign = InfluencerCandidate(handle="us_creator", name="Global", bio="travel vlog", country="US", followers=50_000)
    assert filters.is_local_market(az) is True
    assert filters.is_local_market(foreign) is False


def test_brand_safety_no_false_positive_on_innocent_words():
    b = _brief()
    innocent = InfluencerCandidate(
        handle="alphabet_az", bio="Baku travel blogger",
        followers=40_000,
        evidence=[EvidenceItem(kind="reel", text="alphabet between commerce america", metrics={"likes": 100})],
    )
    score.score_candidates([innocent], b)
    assert innocent.brand_safety >= 9  # 'bet'/'merc' must not match inside words
    assert not any("riskli" in f for f in innocent.flags)


def test_youtube_connector_normalizes_channels_videos_comments(monkeypatch=None):
    orig_get, orig_key = sources_youtube._get, config.YOUTUBE_API_KEY
    sources_youtube._get = _fake_youtube_get
    config.YOUTUBE_API_KEY = "TESTKEY"
    try:
        brief = _brief()
        cands, statuses, seen = sources_youtube.collect(brief, seed_handles=["someone"])
        assert cands, "expected youtube candidates"
        c = cands[0]
        assert c.platform == "youtube"
        assert c.followers == 120_000
        assert c.avatar.startswith("http")
        assert any(e.kind == "video" for e in c.evidence)
        assert any(e.kind == "comment" for e in c.evidence)
        assert c.engagement_rate > 0  # views-based ER computed
        assert all(s.status != "error:disabled" for s in statuses)
    finally:
        sources_youtube._get, config.YOUTUBE_API_KEY = orig_get, orig_key


def test_analyze_deterministic_sentiment_and_bot_flag():
    orig_avail = analyze.llm.available
    analyze.llm.available = lambda: False  # force pandas-only path
    try:
        good = InfluencerCandidate(handle="good_az", evidence=[
            EvidenceItem(kind="comment", text="çox faydalı və real təcrübə", metrics={"is_comment": True}),
            EvidenceItem(kind="comment", text="əla izah etdin təşəkkürlər", metrics={"is_comment": True}),
        ])
        bot = InfluencerCandidate(handle="bot_az", evidence=[
            EvidenceItem(kind="comment", text="wow", metrics={"is_comment": True}),
            EvidenceItem(kind="comment", text="wow", metrics={"is_comment": True}),
            EvidenceItem(kind="comment", text="wow", metrics={"is_comment": True}),
        ])
        analyze.enrich(_brief(), [good, bot])
        assert good.feedback_sentiment > 5
        assert good.audience_summary
        assert any("bot" in f for f in bot.flags)
    finally:
        analyze.llm.available = orig_avail


_IG_PROFILE = {"data": {
    "username": "realtravelaz", "full_name": "Real Travel AZ",
    "biography": "Baku travel blogger", "follower_count": 120000, "media_count": 340,
    "profile_pic_url_hd": "https://img/realtravelaz.jpg", "is_verified": True,
}}
_IG_POSTS = {"data": {"items": [
    {"caption": {"text": "Gürcüstan səyahət"}, "like_count": 3600, "comment_count": 180,
     "play_count": 70000, "code": "ABC123"},
]}}
_TT_PROFILE = {"data": {
    "user": {"uniqueId": "tiktokeraz", "nickname": "TikToker AZ", "signature": "Baku creator",
             "avatarLarger": "https://img/tt.jpg", "verified": False},
    "stats": {"followerCount": 50000, "videoCount": 120, "heartCount": 900000},
}}
_TT_POSTS = {"data": {"videos": [
    {"title": "səyahət vlog", "digg_count": 1000, "comment_count": 50, "play_count": 20000, "video_id": "v1"},
]}}


def test_rapidapi_parses_instagram_profile_and_posts():
    a = sources_rapidapi._IG_SCRAPER_API2
    c = sources_rapidapi.build_profile(a, "realtravelaz", _IG_PROFILE)
    assert c is not None
    assert c.platform == "instagram"
    assert c.handle == "realtravelaz"
    assert c.followers == 120_000
    assert c.posts_count == 340
    assert c.avatar.startswith("http")
    assert "verified" in c.categories
    added = sources_rapidapi.attach_posts(a, c, _IG_POSTS)
    assert added == 1
    post = next(e for e in c.evidence if e.kind == "post")
    assert post.metrics["likes"] == 3600
    assert post.url == "https://www.instagram.com/p/ABC123/"
    sources_rapidapi._merge_metrics(c)
    assert c.engagement_rate > 0


def test_rapidapi_parses_tiktok_nested_paths():
    a = sources_rapidapi._TT_SCRAPER7
    c = sources_rapidapi.build_profile(a, "tiktokeraz", _TT_PROFILE)
    assert c is not None
    assert c.platform == "tiktok"
    assert c.handle == "tiktokeraz"
    assert c.followers == 50_000
    added = sources_rapidapi.attach_posts(a, c, _TT_POSTS)
    assert added == 1
    vid = next(e for e in c.evidence if e.kind == "video")
    assert vid.metrics["video_views"] == 20_000
    assert vid.url == "https://www.tiktok.com/@tiktokeraz/video/v1"


def test_rapidapi_collect_enriches_seeds_offline():
    o_get, o_key, o_dis = sources_rapidapi._get, config.RAPIDAPI_KEY, config.DISABLE_RAPIDAPI
    config.RAPIDAPI_KEY, config.DISABLE_RAPIDAPI = "TESTKEY", False

    def fake_get(adapter, path):
        if "posts" in path:
            return _IG_POSTS
        return _IG_PROFILE

    sources_rapidapi._get = fake_get
    try:
        cands, statuses, seen = sources_rapidapi.collect(
            _brief(), platform="instagram", seed_handles=["realtravelaz"])
        assert cands and cands[0].handle == "realtravelaz"
        assert cands[0].followers == 120_000
        assert seen >= 2  # profile + post
        assert any(s.status == "ok" for s in statuses)
    finally:
        sources_rapidapi._get, config.RAPIDAPI_KEY, config.DISABLE_RAPIDAPI = o_get, o_key, o_dis


def test_rapidapi_skips_without_key_and_needs_handles():
    o_key, o_dis = config.RAPIDAPI_KEY, config.DISABLE_RAPIDAPI
    config.RAPIDAPI_KEY, config.DISABLE_RAPIDAPI = "", False
    try:
        cands, statuses, seen = sources_rapidapi.collect(_brief(), platform="instagram", seed_handles=["x"])
        assert cands == [] and seen == 0
        assert any(s.status == "skipped" for s in statuses)
    finally:
        config.RAPIDAPI_KEY, config.DISABLE_RAPIDAPI = o_key, o_dis
    # with a key but no handles -> honest 'empty', not a crash
    config.RAPIDAPI_KEY, config.DISABLE_RAPIDAPI = "TESTKEY", False
    try:
        cands, statuses, seen = sources_rapidapi.collect(_brief(), platform="tiktok", seed_handles=[])
        assert cands == []
        assert any(s.status == "empty" for s in statuses)
    finally:
        config.RAPIDAPI_KEY, config.DISABLE_RAPIDAPI = o_key, o_dis


def test_orchestrate_registers_tiktok_and_instagram_rapidapi_fallback():
    import orchestrate
    names = {c.name for c in orchestrate.REGISTRY}
    assert "instagram-rapidapi" in names
    assert "tiktok-rapidapi" in names
    assert "tiktok" in orchestrate.platforms()
    ig = sorted([c for c in orchestrate.REGISTRY if c.platform == "instagram"], key=lambda c: c.priority)
    assert ig[0].name == "instagram-apify"  # Apify stays primary
    assert ig[-1].name == "instagram-rapidapi"  # RapidAPI is the fallback


def test_llm_prefers_router_then_falls_back_to_local():
    import llm
    o_router, o_gemini, o_use = llm._via_router, llm._gemini, llm._USE_ROUTER
    # 1) when the router serves, complete() returns its text
    llm._via_router = lambda p, s, t, j: "ROUTED"
    try:
        assert llm.complete("x") == "ROUTED"
    finally:
        llm._via_router = o_router
    # 2) when the router can't serve (None), it falls back to the local provider
    llm._via_router = lambda p, s, t, j: None
    llm._gemini = lambda p, s, t, j: "LOCAL"
    try:
        assert llm.complete("x") == "LOCAL"
    finally:
        llm._via_router, llm._gemini = o_router, o_gemini
    # 3) the router can be disabled entirely (env flag honored)
    llm._USE_ROUTER = False
    try:
        assert llm._via_router("x", "", 0.2, False) is None
    finally:
        llm._USE_ROUTER = o_use


def test_campaign_fit_gate_excludes_off_topic_local_creator():
    good = InfluencerCandidate(
        handle="goodtravelaz",
        bio="Baku travel blogger",
        followers=50_000,
        audience_fit=7.0,
        content_fit=7.0,
        proof_density=4.0,
        total_score=7.0,
    )
    off_topic = InfluencerCandidate(
        handle="foodbloggeraz",
        bio="Baku food blogger",
        followers=50_000,
        audience_fit=4.0,
        content_fit=4.5,
        proof_density=5.0,
        total_score=7.0,
    )
    eligible, filtered_out = filters.apply_eligibility(
        [off_topic, good],
        SelectionFilters(min_followers=20_000),
    )
    assert [c.handle for c in eligible] == ["goodtravelaz"]
    assert [c.handle for c in filtered_out] == ["foodbloggeraz"]
    assert any("kampaniya auditoriyası" in f for f in off_topic.flags)
