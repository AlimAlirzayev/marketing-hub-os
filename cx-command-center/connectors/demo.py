"""Deterministic demo dataset for the Customer Relations Center."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import store
import triage


DEMO_MESSAGES = [
    {
        "source": "chatplace",
        "channel": "instagram_comment",
        "external_id": "demo-ig-001",
        "author_name": "Aysel M.",
        "author_handle": "@aysel_m",
        "text": "3 gündür mesaj yazıram, heç kim cavab vermir. Bu necə xidmətdir?",
        "url": "https://instagram.com/p/demo1",
    },
    {
        "source": "google_business_profile",
        "channel": "google_review",
        "external_id": "demo-google-001",
        "author_name": "Rashad Aliyev",
        "text": "Hadisədən sonra ödəniş prosesi çox gecikir. Operatorlar dəqiq məlumat vermir.",
        "rating": 1,
        "url": "https://maps.google.com/?cid=demo",
    },
    {
        "source": "chatplace",
        "channel": "tiktok_comment",
        "external_id": "demo-tt-001",
        "author_handle": "@driver.az",
        "text": "Qiymət niyə belə bahalıdır? Rəqiblərdə daha sərfəlidir.",
        "url": "https://tiktok.com/@demo/video/1",
    },
    {
        "source": "website",
        "channel": "website_form",
        "external_id": "demo-web-001",
        "author_name": "Nigar",
        "text": "Saytda ödəniş keçmir, kartdan pul tutuldu amma polis görünmür.",
    },
    {
        "source": "telegram",
        "channel": "telegram",
        "external_id": "demo-tg-001",
        "author_name": "Elvin",
        "text": "Filialda əməkdaş çox kobud danışdı. Məsələyə baxılmasını istəyirəm.",
    },
    {
        "source": "facebook",
        "channel": "facebook_comment",
        "external_id": "demo-fb-001",
        "author_name": "Samir Q.",
        "text": "Bu məsələ həll olunmasa media səhifələrində paylaşacam. Artıq bezmişəm.",
        "url": "https://facebook.com/demo/posts/1",
    },
    {
        "source": "email",
        "channel": "email",
        "external_id": "demo-mail-001",
        "author_name": "Leyla",
        "text": "Müqavilə şərtlərində izah edilməyən istisnaya görə imtina aldım.",
    },
    {
        "source": "whatsapp",
        "channel": "whatsapp",
        "external_id": "demo-wa-001",
        "author_name": "Orxan",
        "text": "Salam, müraciətimin statusunu bilmək istəyirəm. Dünən sənəd göndərmişdim.",
    },
    {
        "source": "google_business_profile",
        "channel": "google_review",
        "external_id": "demo-google-002",
        "author_name": "Gunel H.",
        "text": "Problemimi tez həll etdilər. Təşəkkür edirəm.",
        "rating": 5,
        "url": "https://maps.google.com/?cid=demo2",
    },
    {
        "source": "web_listening",
        "channel": "web_mention",
        "external_id": "demo-webmention-001",
        "author_name": "Forum user",
        "text": "Xalq Sigorta ilə bağlı gecikmə şikayətləri yenə çoxalıb.",
        "url": "https://forum.example.com/demo",
    },
]


def seed_if_empty() -> None:
    if store.count_all():
        return
    base = datetime.now(timezone.utc) - timedelta(days=8)
    for idx, message in enumerate(DEMO_MESSAGES):
        payload = dict(message)
        payload["_skip_ai"] = True
        payload["occurred_at"] = (base + timedelta(hours=idx * 17)).replace(microsecond=0).isoformat()
        result = triage.triage_message(payload)
        store.upsert_complaint(payload, result)
