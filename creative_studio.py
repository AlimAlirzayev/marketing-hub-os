"""Kreativ Studio — the merged creative module for the unified dashboard.

This is the "two art directors fused into one": it takes the old Social & Kreativ
Studio's automatic image generation (Imagen 3 via visual_studio) and fuses it
with Atelier's brain — brand-DNA-grounded 11-layer prompts, an AI vision
critique, and an A/B compare board — all native Streamlit inside the single OS
frontend (port 8501). No separate server, no iframe.

Image engines (both ride existing keys/subscriptions, no new paid API):
  • Imagen 3  — one-click, via the same GEMINI_API_KEY the whole OS uses.
  • ChatGPT Bridge — generate in your ChatGPT Business UI, upload the result.
If Imagen fails (quota/billing), the Bridge path is always available — no silent
drops.
"""

from __future__ import annotations

import os
import subprocess
import sys

import streamlit as st

from atelier import brand, critique, imagegen, lab

_ROOT = os.path.dirname(os.path.abspath(__file__))


def _bridge_open_chrome(profile: str) -> None:
    """Open a debug-port Chrome so the bridge can ATTACH to your logged-in session
    (instead of a fresh empty browser)."""
    try:
        subprocess.Popen([sys.executable, "-m", "atelier.web_bridge",
                          "--open-chrome", "--profile", profile], cwd=_ROOT)
        if profile == "real":
            st.info("Debug Chrome açılır (real profil — mövcud loginlərin). Boş açılırsa, "
                    "əvvəlcə bütün adi Chrome pəncərələrini bağla və yenidən bas.")
        else:
            st.info("Debug Chrome açılır (ayrıca profil). Gemini/ChatGPT-yə bir dəfə login ol, açıq saxla.")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Chrome açıla bilmədi: {exc}")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _safe_index(options: list, value, default: int = 0) -> int:
    try:
        return options.index(value)
    except (ValueError, AttributeError):
        return default


def _init_state() -> dict:
    if "cs" not in st.session_state:
        st.session_state.cs = {
            "concepts": [], "meta": {}, "source": None,
            "images": {}, "critiques": {}, "selected": set(),
        }
    st.session_state.setdefault("cs_brief", "")
    return st.session_state.cs


def _store_image(cs: dict, idx: int, data: bytes, mime: str, engine: str,
                 path: str | None) -> None:
    cs["images"][idx] = {"bytes": data, "mime": mime, "engine": engine,
                         "path": path, "nbytes": len(data)}
    cs["critiques"].pop(idx, None)  # a new image invalidates the old critique


def _score_color(s) -> str:
    if s is None:
        return "#8A8A93"
    return "#16A34A" if s >= 80 else "#F59E0B" if s >= 60 else "#E31E24"


def _engine_caption(engine_id: str) -> str:
    if engine_id == "upload":
        return "ChatGPT Bridge"
    e = imagegen.get(engine_id)
    return e.label if e else engine_id


# --------------------------------------------------------------------------
# Brand Brain (compact, editable)
# --------------------------------------------------------------------------
def _brand_brain(bp: dict) -> dict:
    state = bp["state"]
    with st.expander("🧠 Brand Brain — aktiv DNA və House Rules", expanded=False):
        styles = {s["key"]: s for s in bp["styles"]}
        voices = {v["key"]: v for v in bp["voices"]}
        st.caption("Bütün konseptlər bu seçimlərdən doğur. Dəyişiklik yadda saxlananda bütün OS üçün keçərlidir.")

        c1, c2 = st.columns(2)
        if state["active_style"] in styles:
            c1.markdown(f"**Vizual DNA:** {styles[state['active_style']]['title']}")
            c1.caption(styles[state["active_style"]]["summary"])
        if state["active_voice"] in voices:
            c2.markdown(f"**Səs DNA:** {voices[state['active_voice']]['title']}")
            c2.caption(voices[state["active_voice"]]["summary"])

        house = st.text_area("House Rules (hər prompt-a əlavə olunan öz qaydaların)",
                             value=state.get("house_rules", ""), key="cs_house", height=80)
        excl = st.text_area("Əlavə qadağalar (exclusions)",
                            value=state.get("extra_exclusions", ""), key="cs_excl", height=60)
        if st.button("💾 House Rules-u yadda saxla", key="cs_save_rules"):
            new_state = brand.save_state({"house_rules": house, "extra_exclusions": excl})
            st.session_state.cs_brand = brand.payload()
            st.success("Yadda saxlanıldı.")
            return new_state
    return state


# --------------------------------------------------------------------------
# Concept rendering
# --------------------------------------------------------------------------
def _generate_engine(cs: dict, c: dict, engine_id: str, fmt_label: str) -> None:
    eng = imagegen.get(engine_id)
    name = eng.label if eng else engine_id
    with st.spinner(f"{name} şəkli yaradır… (bir neçə saniyə)"):
        res = imagegen.generate(engine_id, c["prompt"], fmt_label)
    if res.get("ok"):
        _store_image(cs, c["idx"], res["bytes"], res["mime"], engine_id, None)
    else:
        st.error(
            f"{name} alınmadı (limit/billing/safety ola bilər): {res.get('error')}. "
            "Başqa mühərrik seç və ya ChatGPT Bridge ilə əl ilə yüklə.")


def _run_critique(cs: dict, c: dict) -> None:
    img = cs["images"].get(c["idx"])
    if not img:
        return
    with st.spinner("AI art-director şəkli qiymətləndirir…"):
        cs["critiques"][c["idx"]] = critique.review(
            img["bytes"], img["mime"], angle=c["angle"],
            prompt_excerpt=c["prompt"][:600], style_key=cs["meta"].get("style", ""))


def _render_critique(cr: dict) -> None:
    cols = st.columns([1, 4])
    if cr.get("score") is not None:
        cols[0].markdown(
            f"<div style='font-size:30px;font-weight:800;color:{_score_color(cr['score'])}'>"
            f"{cr['score']}</div><div style='color:#888;font-size:11px'>BAL</div>",
            unsafe_allow_html=True)
    cols[1].markdown(f"**{cr.get('verdict','')}**  \n"
                     f"<span style='color:#888'>{cr.get('brand_fit','')}</span>",
                     unsafe_allow_html=True)
    if cr.get("strengths"):
        st.markdown("✅ **Yaxşı:** " + " · ".join(cr["strengths"]))
    if cr.get("fixes"):
        st.markdown("🛠 **Düzəliş:** " + " · ".join(cr["fixes"]))
    if cr.get("ai_tells"):
        st.markdown(":red[⚠ **AI-tells:** " + " · ".join(cr["ai_tells"]) + "]")
    ov = cr.get("overlay", {})
    mark = lambda v: "✓" if v is True else "✗" if v is False else "—"
    st.caption(f"Başlıq sahəsi {mark(ov.get('top_left_clear'))}  ·  "
               f"Footer sahəsi {mark(ov.get('bottom_clear'))}  ·  mənbə: {cr.get('source')}")


def _render_card(cs: dict, c: dict) -> None:
    idx = c["idx"]
    with st.container(border=True):
        head = st.columns([6, 1])
        head[0].markdown(
            f"**{c['angle']}**  \n<span style='color:#888'>{c.get('rationale','')}</span>",
            unsafe_allow_html=True)
        sel = head[1].checkbox("⭐", value=idx in cs["selected"], key=f"cs_sel_{idx}")
        (cs["selected"].add if sel else cs["selected"].discard)(idx)

        with st.expander("📋 Prompt", expanded=False):
            st.code(c["prompt"], language="text")
        if c.get("caption"):
            st.text_area("Caption (AZ)", value=c["caption"], key=f"cs_cap_{idx}", height=90)

        engine_id = st.session_state.get("cs_engine", "gemini-2.5-flash-image")
        fmt_label = cs.get("meta", {}).get("format", "4:5 Feed")
        gen_col, up_col = st.columns(2)
        if gen_col.button("🎨 Şəkil yarat", key=f"cs_gen_{idx}", use_container_width=True):
            _generate_engine(cs, c, engine_id, fmt_label)
        up = up_col.file_uploader("↗ ChatGPT-də yarat, şəkli yüklə",
                                  type=["png", "jpg", "jpeg", "webp"], key=f"cs_up_{idx}")
        if up is not None:
            data = up.getvalue()
            if cs["images"].get(idx, {}).get("nbytes") != len(data):
                _store_image(cs, idx, data, up.type or "image/png", "upload", None)

        img = cs["images"].get(idx)
        if img:
            st.image(img["bytes"], use_container_width=True,
                     caption=f"Mənbə: {_engine_caption(img['engine'])}")
            if st.button("✦ Qiymətləndir", key=f"cs_crit_{idx}", use_container_width=True):
                _run_critique(cs, c)
            cr = cs["critiques"].get(idx)
            if cr:
                _render_critique(cr)


def _render_gallery(cs: dict) -> None:
    have = [c for c in cs["concepts"] if c["idx"] in cs["images"]]
    if not have:
        st.info("Hələ şəkil yoxdur. Kartlar rejimində Imagen 3 ilə yarat və ya yüklə — "
                "sonra burada yan-yana müqayisə edə bilərsən.")
        return
    cols = st.columns(3)
    for i, c in enumerate(have):
        idx = c["idx"]
        img = cs["images"][idx]
        cr = cs["critiques"].get(idx, {})
        with cols[i % 3]:
            star = "⭐ " if idx in cs["selected"] else ""
            st.image(img["bytes"], use_container_width=True)
            badge = f" · :{'green' if (cr.get('score') or 0)>=80 else 'orange'}[{cr.get('score')}]" \
                if cr.get("score") is not None else ""
            st.markdown(f"{star}**{c['angle']}**{badge}")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def render() -> None:
    st.title("🎨 Kreativ Studio")
    st.write("Brend DNA + 11-qatlı prompt + Imagen 3 / ChatGPT Bridge + AI critique — "
             "vahid yaradıcı mühit. (Social Studio + Atelier birləşdi.)")

    if "cs_brand" not in st.session_state:
        st.session_state.cs_brand = brand.payload()
    bp = st.session_state.cs_brand
    cs = _init_state()

    state = _brand_brain(bp)

    # ---- Composer ----
    with st.container(border=True):
        st.text_area("Brief", key="cs_brief",
                     placeholder="məs: KASKO Bayram push, Azpetrol partnyorluğu, təcili müraciət hissi")
        c1, c2, c3, c4 = st.columns(4)
        style_keys = [s["key"] for s in bp["styles"]]
        style_lbl = {s["key"]: s["title"] for s in bp["styles"]}
        style = c1.selectbox("Style DNA", style_keys, key="cs_style",
                             index=_safe_index(style_keys, state["active_style"]),
                             format_func=lambda k: style_lbl.get(k, k))
        fmt = c2.selectbox("Format", bp["formats"], key="cs_fmt",
                           index=_safe_index(bp["formats"], state["default_format"]))
        dialect = c3.selectbox("Model", bp["dialects"], key="cs_dialect",
                               index=_safe_index(bp["dialects"], state["active_dialect"]))
        n = c4.selectbox("Konsept", [2, 3, 4, 6], key="cs_n",
                         index=_safe_index([2, 3, 4, 6], int(state.get("default_n", 4))))

        cc1, cc2 = st.columns([1, 2])
        with_caption = cc1.checkbox("Caption (AZ) yaz", value=True, key="cs_wc")
        voice_keys = [v["key"] for v in bp["voices"]]
        voice_lbl = {v["key"]: v["title"] for v in bp["voices"]}
        voice = cc2.selectbox("Voice DNA (caption üçün)", voice_keys, key="cs_voice",
                              index=_safe_index(voice_keys, state["active_voice"]),
                              format_func=lambda k: voice_lbl.get(k, k))

        eng_list = imagegen.list_engines()
        eng_ids = [e.id for e in eng_list]
        eng_lbl = {e.id: imagegen.engine_label(e) for e in eng_list}
        st.selectbox("🎨 Şəkil mühərriki (bütün konseptlər üçün)", eng_ids, key="cs_engine",
                     index=_safe_index(eng_ids, "gemini-2.5-flash-image"),
                     format_func=lambda k: eng_lbl.get(k, k))
        st.caption("`cheap`/`paid` = Gemini API (billing lazımdır). `abunəlik` = sənin Gemini/ChatGPT "
                   "abunəliyini brauzerdə işlədir (yeni ödəniş yox). `əl ilə` = ChatGPT-də yarat, yüklə.")
        with st.expander("🌐 Abunəlik bridge — Chrome-u qoş (mövcud loginlərlə)", expanded=False):
            st.caption("`abunəlik` mühərrikləri sənin Chrome sessiyana QOŞULUR — yeni boş brauzer yox. "
                       "Bunun üçün Chrome bir dəfə debug rejimində açılmalıdır:")
            b1, b2 = st.columns(2)
            if b1.button("🔓 Mövcud loginlərlə aç (real profil)", key="cs_chrome_real",
                         use_container_width=True):
                _bridge_open_chrome("real")
            if b2.button("➕ Ayrıca profil aç (bir dəfə login)", key="cs_chrome_bridge",
                         use_container_width=True):
                _bridge_open_chrome("bridge")
            st.caption("• **Real profil:** bütün loginlərin hazırdır — amma əvvəlcə adi Chrome-u tam bağla "
                       "(profil kilidi). • **Ayrıca profil:** adi Chrome açıq qala bilər, bir dəfə login ol. "
                       "Açılan Chrome-da Gemini/ChatGPT-ni aç, sonra `abunəlik` mühərriki ilə şəkil yarat.")

        if st.button("✨ Konsept yarat", type="primary", use_container_width=True):
            brief = st.session_state.cs_brief.strip()
            if not brief:
                st.warning("Brief yazın.")
            else:
                with st.spinner("AI art-director konseptləri qurur…"):
                    res = lab.compose(brief, style, voice, dialect, fmt, n, with_caption,
                                      house_rules=state.get("house_rules", ""),
                                      extra_exclusions=state.get("extra_exclusions", ""))
                cs.update({"concepts": res["concepts"], "meta": res["meta"],
                           "source": res["source"], "images": {}, "critiques": {},
                           "selected": set()})

    # ---- Board ----
    if not cs["concepts"]:
        st.info("Brief yazıb **Konsept yarat**-a basın. Hər konsept üçün hazır prompt alıb "
                "bir kliklə Imagen 3 ilə şəkil yarada və ya ChatGPT-də yaradıb yükləyə bilərsiniz.")
        return

    if cs["source"] == "gemini":
        st.success("AI art-director konseptləri (Gemini)", icon="✅")
    else:
        st.warning("Şablon konseptləri (AI offline) — yenə brendə uyğun.", icon="⚠️")

    view = st.radio("Görünüş", ["Kartlar", "Qalereya (müqayisə)"],
                    horizontal=True, label_visibility="collapsed", key="cs_view")
    if view.startswith("Qalereya"):
        _render_gallery(cs)
    else:
        for c in cs["concepts"]:
            _render_card(cs, c)
