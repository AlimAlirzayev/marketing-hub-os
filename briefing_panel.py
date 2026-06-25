"""Executive Daily Briefing panel for the Bas Iqametgah dashboard.

Renders the real, source-labelled leadership report inside Streamlit. All
numbers come from scripts/daily_briefing.py collectors (cx-command-center +
ads-studio live Meta). Nothing here is hardcoded: where a source is demo or
unavailable, the panel says so with a badge instead of inventing data.
"""

from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = ROOT_DIR / "scripts"
BRIEFINGS_DIR = ROOT_DIR / "output" / "briefings"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import daily_briefing as briefing  # noqa: E402


# --- source status badges --------------------------------------------------

_BADGE = {
    "live": ("🟢", "CANLI"),
    "demo": ("🟡", "DEMO"),
    "missing": ("⚪", "QOŞULMAYIB"),
    "error": ("🔴", "ƏLÇATMAZ"),
}


def _badge(kind: str) -> str:
    icon, label = _BADGE.get(kind, _BADGE["error"])
    return f"{icon} **{label}**"


def _num(value, digits: int = 0) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.{digits}f}".replace(",", " ")
    except (TypeError, ValueError):
        return str(value)


@st.cache_data(ttl=600, show_spinner=False)
def _collect_cached() -> tuple[dict, dict]:
    """10-minute cached collection so the panel is instant on repeat views.
    The Refresh button clears this cache for a forced live pull."""
    return briefing.collect_all()


def get_data() -> tuple[dict, dict]:
    """Public, cached accessor so other panels (e.g. the landing KPIs) reuse
    the same real collection instead of duplicating or faking numbers."""
    return _collect_cached()


# --- section renderers -----------------------------------------------------

def _render_sources(cx: dict, ads: dict) -> None:
    cx_mode = cx.get("mode", "error") if cx.get("status") == "ok" else "error"
    ads_mode = ads.get("mode", "error") if ads.get("status") == "ok" else "error"
    cx_kind = {"live": "live", "demo": "demo"}.get(cx_mode, "error")
    ads_kind = {"live": "live", "demo": "demo"}.get(ads_mode, "error")

    st.markdown("#### Mənbə statusu")
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"{_badge(cx_kind)}\n\nCX / Şikayətlər")
    c2.markdown(f"{_badge(ads_kind)}\n\nMeta Ads")
    c3.markdown(f"{_badge('missing')}\n\nGoogle Reviews")
    c4.markdown(f"{_badge('missing')}\n\nSosial dinləmə")
    st.caption(
        "Yalnız qoşulmuş sistemlərdən oxunan real data göstərilir. "
        "DEMO/QOŞULMAYIB bölmələrdə rəqəm uydurulmur — boşluq açıq qeyd olunur."
    )


def _render_kpis(cx: dict, ads: dict) -> None:
    st.markdown("#### Əsas göstəricilər")
    k1, k2, k3, k4 = st.columns(4)

    if cx.get("status") == "ok":
        t24 = cx["last24h"]["totals"]
        t7 = cx["last7d"]["totals"]
        suffix = " · demo" if cx.get("mode") == "demo" else ""
        k1.metric("Şikayət (24s)", _num(t24["messages"]), f"{t7['messages']} / 7g{suffix}")
        k2.metric(
            "Açıq / Kritik",
            f"{t24['open']} / {t24['critical_open']}",
            f"{t7['overdue']} SLA gecikmə",
            delta_color="inverse",
        )
        risk = t7["risk_score"]
        level = {"red": "🔴 Qırmızı", "amber": "🟡 Sarı", "green": "🟢 Yaşıl"}.get(
            cx["brief"]["level"], cx["brief"]["level"]
        )
        k3.metric("Reputasiya riski", f"{risk}/100", level, delta_color="off")
    else:
        k1.metric("Şikayət (24s)", "—", "mənbə əlçatmaz")
        k2.metric("Açıq / Kritik", "—")
        k3.metric("Reputasiya riski", "—")

    if ads.get("status") == "ok" and ads.get("mode") == "live":
        mt = ads["month_totals"]
        cur = ads.get("currency", "AZN")
        k4.metric(
            f"Meta xərc (ay, {cur})",
            _num(mt.get("spend"), 2),
            f"{_num(mt.get('leads'))} lead · {_num(mt.get('messages'))} mesaj",
            delta_color="off",
        )
    else:
        k4.metric("Meta xərc (ay)", "—", "demo / əlçatmaz")


def _render_complaints(cx: dict) -> None:
    st.markdown("### 1. Müştəri şikayətləri")
    if cx.get("status") != "ok":
        st.error(f"CX Command Center oxuna bilmədi: `{cx.get('detail', '?')}`")
        return
    if cx.get("mode") == "demo":
        st.warning(
            "Bu rəqəmlər **test datasıdır** (CX_DATA_MODE=demo). Real şikayət axını "
            "üçün Chatplace/Meta webhookları qoşulmalıdır — aşağıdakılar yalnız "
            "sistemin işlədiyini göstərir."
        )
    channels = cx["last7d"]["breakdowns"]["channel"]
    causes = cx["last7d"]["root_causes"]
    col1, col2 = st.columns(2)
    with col1:
        st.caption("Kanallar (7 gün)")
        if channels:
            df = pd.DataFrame(channels).rename(columns={"key": "kanal", "count": "say"})
            st.bar_chart(df.set_index("kanal"), height=240)
        else:
            st.info("Kanal datası yoxdur.")
    with col2:
        st.caption("Əsas səbəblər → məsul komanda")
        if causes:
            df = pd.DataFrame(
                [{"səbəb": c["category"], "say": c["count"], "komanda": c["team"]} for c in causes]
            )
            st.dataframe(df, use_container_width=True, hide_index=True, height=240)
        else:
            st.info("Səbəb datası yoxdur.")


def _render_reputation(cx: dict) -> None:
    st.markdown("### 2. Reputasiya riski")
    if cx.get("status") != "ok":
        st.error("CX datası olmadan risk qiymətləndirilmir.")
        return
    brief = cx["brief"]
    t7 = cx["last7d"]["totals"]
    level = {"red": "error", "amber": "warning", "green": "success"}.get(brief["level"], "info")
    getattr(st, level)(
        f"**Risk indeksi: {t7['risk_score']}/100** — {brief['title']}\n\n{brief['text']}"
    )
    st.caption(
        f"Neqativ siqnal (7 gün): {t7['negative']} / {t7['messages']}"
        + ("  ·  demo data üzərində" if cx.get("mode") == "demo" else "")
    )


def _render_sales(ads: dict) -> None:
    st.markdown("### 3. Satış fürsətləri / Paid media")
    if ads.get("status") != "ok":
        st.error(f"Meta connector xətası: `{ads.get('detail', '?')}`")
        return
    if ads.get("mode") != "live":
        st.info("Meta hesabı qoşulmayıb (demo) — bu bölmə üçün real data yoxdur.")
        return
    cur = ads.get("currency", "AZN")
    st.caption(f"Hesab: {ads.get('account_name', ads.get('account'))} · {ads.get('account')}")

    daily = ads.get("daily") or []
    if daily:
        df = pd.DataFrame(daily)
        cols = [c for c in ("date", "spend", "clicks", "leads", "messages") if c in df.columns]
        df = df[cols].set_index("date")
        st.caption(f"Son günlər (xərc {cur} / klik / lead / mesaj)")
        st.dataframe(df, use_container_width=True)

    campaigns = ads.get("campaigns") or []
    active = [c for c in campaigns if float(c.get("spend") or 0) > 0]
    if active:
        st.caption("Aktiv kampaniyalar (bu ay)")
        df = pd.DataFrame(
            [
                {
                    "kampaniya": c["campaign_name"],
                    f"xərc ({cur})": round(float(c.get("spend") or 0), 2),
                    "CTR %": round(float(c.get("ctr") or 0), 2),
                    "lead": c.get("leads"),
                    "mesaj": c.get("messages"),
                }
                for c in active[:8]
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.warning(
            "Bu ay heç bir kampaniya xərc etməyib — hesabda aktiv çatdırılma yoxdur. "
            "Hazır draft varsa, yayımlanmaması birbaşa itirilmiş fürsətdir."
        )


def _render_social(cx: dict, ads: dict) -> None:
    st.markdown("### 4. Sosial media siqnalları")
    st.caption("Ayrıca sosial dinləmə aləti qoşulmayıb — görünən siqnallar məhduddur.")
    if ads.get("status") == "ok" and ads.get("mode") == "live":
        bp = ads.get("by_platform") or {}
        rows = []
        for key in ("facebook", "instagram", "messenger"):
            p = bp.get(key) or {}
            if float(p.get("impressions") or 0) > 0:
                rows.append(
                    {"platforma": key, "göstərim": p.get("impressions"), "klik": p.get("clicks")}
                )
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.info("TikTok, forumlar, rəqib fəaliyyəti: **data yoxdur** — qiymətləndirmə verilmir.")


def _render_actions(cx: dict, ads: dict) -> None:
    st.markdown("### 5. Prioritet addımlar (data-əsaslı)")
    actions = briefing.build_actions(cx, ads)
    for i, action in enumerate(actions, 1):
        st.markdown(f"**{i}.** {action}")


def _render_archive() -> None:
    st.markdown("### 🗂 Arxiv")
    if not BRIEFINGS_DIR.exists():
        st.caption("Hələ saxlanmış hesabat yoxdur.")
        return
    files = sorted(BRIEFINGS_DIR.glob("briefing-*.md"), reverse=True)
    if not files:
        st.caption("Hələ saxlanmış hesabat yoxdur.")
        return
    names = [f.name for f in files]
    chosen = st.selectbox("Keçmiş hesabatlar", names, key="briefing_archive_pick")
    if chosen:
        text = (BRIEFINGS_DIR / chosen).read_text(encoding="utf-8")
        with st.expander(f"📄 {chosen}", expanded=False):
            st.markdown(text)


# --- public entry point ----------------------------------------------------

def render() -> None:
    st.title("📋 Gündəlik Rəhbərlik Hesabatı")
    st.write(
        "İcraçı direktor üçün son 24 saatın real mənzərəsi: müştəri şikayətləri, "
        "reputasiya riski, satış fürsətləri, sosial siqnallar və prioritet addımlar."
    )

    top_l, top_r = st.columns([3, 1])
    with top_r:
        if st.button("🔄 Canlı yenilə", use_container_width=True):
            _collect_cached.clear()
            st.session_state.pop("briefing_md", None)

    with st.spinner("Real kollektorlar işləyir (CX + Meta canlı)..."):
        try:
            cx, ads = _collect_cached()
        except Exception as exc:  # collection should never crash the panel
            st.error(f"Kollektor xətası: {type(exc).__name__}: {exc}")
            return

    with top_l:
        st.caption(f"Sonuncu yığım: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

    _render_sources(cx, ads)
    st.divider()
    _render_kpis(cx, ads)
    st.divider()
    _render_complaints(cx)
    st.divider()
    _render_reputation(cx)
    st.divider()
    _render_sales(ads)
    st.divider()
    _render_social(cx, ads)
    st.divider()
    _render_actions(cx, ads)
    st.divider()

    # Export + persist the full markdown report.
    md = briefing.render(cx, ads)
    st.session_state["briefing_md"] = md
    e1, e2 = st.columns(2)
    e1.download_button(
        "⬇️ Markdown yüklə",
        data=md,
        file_name=f"briefing-{date.today().isoformat()}.md",
        mime="text/markdown",
        use_container_width=True,
    )
    if e2.button("💾 Arxivə saxla", use_container_width=True):
        BRIEFINGS_DIR.mkdir(parents=True, exist_ok=True)
        out = BRIEFINGS_DIR / f"briefing-{date.today().isoformat()}.md"
        out.write_text(md, encoding="utf-8")
        st.success(f"Saxlanıldı: output/briefings/{out.name}")

    _render_archive()
