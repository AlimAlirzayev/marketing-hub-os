import streamlit as st
import pandas as pd
import time
import sys
from pathlib import Path

# Xalq Insurance Digital OS modullarını import edə bilmək üçün ana qovluğu sistem yoluna əlavə edirik
ROOT_DIR = Path(__file__).resolve().parent
sys.path.append(str(ROOT_DIR))
sys.path.append(str(ROOT_DIR / "cx-command-center"))

import triage

st.set_page_config(
    page_title="Xalq Insurance Digital OS · Baş İqamətgah",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Sol Menyu (Sidebar)
st.sidebar.title("Xalq Insurance Digital OS")
st.sidebar.caption("Avtonom Əməliyyat Sistemi v2.0")
st.sidebar.divider()

MODULES = [
    "🌐 Baş İqamətgah",
    "📋 Gündəlik Hesabat",
    "🤖 AI Agent Terminalı",
    "Agent Radar (Security)",
    "🎧 Customer Relations Center", 
    "📈 Ads & Performans",
    "🛒 Price Hunter (Rəqabət)",
    "🎯 Influencer Hunter",
    "📚 Bilik Bazası (RAG)",
    "🎨 Kreativ Studio"
]

# 1. Düzgün State Management (Routing) qurulur
if "active_tab" not in st.session_state:
    st.session_state.active_tab = MODULES[0]

def switch_tab(tab_name):
    st.session_state.active_tab = tab_name

menu = st.sidebar.radio(
    "Modullar",
    options=MODULES,
    index=MODULES.index(st.session_state.active_tab),
    key="active_tab" # Bu, Radio düyməsini birbaşa session_state-ə bağlayır
)

st.sidebar.divider()
st.sidebar.info("Sistem Statusu: **Aktiv** 🟢\n\nBütün agentlər dinləmədədir.")

if menu == "🌐 Baş İqamətgah":
    st.title("🌐 Xalq Insurance Digital OS · Baş İqamətgah")
    st.markdown("Xalq Sığorta üçün Avtonom Marketinq, Rəqabət və Müştəri Təcrübəsi Ekosistemi. Aşağıda sistemin ümumi vəziyyəti ilə tanış ola bilərsiniz.")
    
    # Əsas KPI-lar — real kollektorlardan (CX + Meta canlı). Data əlçatmazsa
    # rəqəm uydurulmur, "—" göstərilir.
    import briefing_panel
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    try:
        _cx, _ads = briefing_panel.get_data()
    except Exception:
        _cx, _ads = {"status": "error"}, {"status": "error"}

    kpi1.metric(label="Aktiv Modullar", value=str(len(MODULES) - 1))

    if _cx.get("status") == "ok":
        _t = _cx["last7d"]["totals"]
        _src = "demo" if _cx.get("mode") == "demo" else "canlı"
        kpi2.metric("Açıq Şikayət (CX)", str(_t["open"]),
                    f"{_t['overdue']} SLA gecikmə · {_src}", delta_color="inverse")
        _risk = _t["risk_score"]
        _lvl = {"red": "🔴", "amber": "🟡", "green": "🟢"}.get(_cx["brief"]["level"], "")
        kpi4.metric("Reputasiya riski", f"{_risk}/100", _lvl, delta_color="off")
    else:
        kpi2.metric("Açıq Şikayət (CX)", "—", "əlçatmaz")
        kpi4.metric("Reputasiya riski", "—")

    if _ads.get("status") == "ok" and _ads.get("mode") == "live":
        _mt = _ads["month_totals"]
        _cur = _ads.get("currency", "AZN")
        kpi3.metric(f"Meta Xərc (ay, {_cur})", briefing_panel._num(_mt.get("spend"), 2),
                    f"{briefing_panel._num(_mt.get('leads'))} lead · canlı", delta_color="off")
    else:
        kpi3.metric("Meta Xərc (ay)", "—", "demo / əlçatmaz")

    st.markdown("### 🧩 Aktiv Modullar üzrə Canlı Vəziyyət")

    # Home-page module cards are data-driven: adding a module is a one-line entry
    # below, not a new copy-pasted `with col...` block. Cards that surface live
    # data expose a `caption` callable; static cards simply omit it.
    def _cx_caption():
        if _cx.get("status") == "ok":
            _t7 = _cx["last7d"]["totals"]
            st.caption(f"7 gün: {_t7['messages']} siqnal · həll {_t7['resolution_rate']}% · "
                       f"orta reytinq {_t7['avg_rating'] if _t7['avg_rating'] is not None else '—'}"
                       + ("  · demo" if _cx.get("mode") == "demo" else ""))
        else:
            st.caption("CX datası əlçatmaz.")

    def _ads_caption():
        if _ads.get("status") == "ok" and _ads.get("mode") == "live":
            _amt = _ads["month_totals"]
            _acur = _ads.get("currency", "AZN")
            st.caption(f"Bu ay: {briefing_panel._num(_amt.get('spend'), 2)} {_acur} xərc · "
                       f"{briefing_panel._num(_amt.get('clicks'))} klik · canlı")
        else:
            st.caption("Meta datası demo / əlçatmaz.")

    home_cards = [
        {
            "title": "🎧 Customer Relations Center (Triage)",
            "desc": "Süni intellekt rəyləri (Google, Instagram, Facebook) oxuyur, SLA və sentiment (hiss) analizi edir.",
            "caption": _cx_caption,
            "button": "Customer Relations Center panelinə keçid",
            "key": "cx_btn",
            "target": "🎧 Customer Relations Center",
        },
        {
            "title": "📈 Ads Studio Analitikası",
            "desc": "Meta API üzərindən reklam büdcəsi, CPL və göstərilmələr avtomatik monitorinq edilir.",
            "caption": _ads_caption,
            "button": "Ads Panelinə Keçid",
            "key": "ads_btn",
            "target": "📈 Ads & Performans",
        },
        {
            "title": "🛒 Price Hunter",
            "desc": "Rəqiblərin qiymət monitorinqi, endirimlər və bazar anomaliyalarının avtomatik izlənməsi.",
            "button": "Bazar İzləməsinə Keçid",
            "key": "price_btn",
            "target": "🛒 Price Hunter (Rəqabət)",
        },
        {
            "title": "Agent Radar (Security)",
            "desc": "Automatic governance scan ranks which agent workflow is worth building next, without granting access.",
            "button": "Open Agent Radar",
            "key": "agent_radar_btn",
            "target": "Agent Radar (Security)",
        },
        {
            "title": "🎯 Influencer Hunter",
            "desc": "Instagram creator-larını brief, Reels/post sübutları, feedback və brand-safety kriteriyaları ilə shortlist edir.",
            "button": "Influencer Hunter-a Keçid",
            "key": "influencer_btn",
            "target": "🎯 Influencer Hunter",
        },
        {
            "title": "🤖 AI Agent Terminalı",
            "desc": "Background proseslərə (Browser, Tool Calling, Content Gen) interaktiv əmr mərkəzi.",
            "button": "Terminala Keçid",
            "key": "agent_btn",
            "target": "🤖 AI Agent Terminalı",
        },
    ]

    # Fresh columns per row so cards stay vertically aligned even when the
    # left/right card heights differ (re-using one column pair would not).
    for _row_start in range(0, len(home_cards), 2):
        _cols = st.columns(2)
        for _col, _card in zip(_cols, home_cards[_row_start:_row_start + 2]):
            with _col.container(border=True):
                st.subheader(_card["title"])
                st.write(_card["desc"])
                if _card.get("caption"):
                    _card["caption"]()
                st.button(
                    _card["button"],
                    key=_card["key"],
                    on_click=switch_tab,
                    args=(_card["target"],),
                    use_container_width=True,
                )

elif menu == "📋 Gündəlik Hesabat":
    import briefing_panel
    briefing_panel.render()

elif menu == "🤖 AI Agent Terminalı":
    st.title("🤖 Agent Terminalı")
    st.write("Tapşırığı AI Council-ə göndərin: Codex, Gemini və Claude Code birlikdə plan qurur, sonra sistem işi icra edir.")
    
    from gateway import database as db
        
    messages = db.get_agent_messages()
    for msg in messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    if prompt := st.chat_input("Tapşırıq verin (məsələn: 'kampaniya skripti yarat'):"):
        db.add_agent_message("user", prompt)
        with st.chat_message("user"):
            st.markdown(prompt)
            
        with st.chat_message("assistant"):
            with st.spinner("AI Council toplanır, plan qurur və icraya keçir..."):
                # Gateway modulu ilə əlaqə qururuq
                from gateway.executor import execute
                from gateway.queue import Job
                
                job = Job(
                    id=int(time.time()), source="dashboard", chat_id=None,
                    task=prompt, status="running", result=None, error=None,
                    artifacts=[], created_at=time.time(), started_at=time.time(),
                    finished_at=None
                )
                result = execute(job)
                response_text = result["result"]
                
                st.markdown(response_text)
                if result.get("artifacts"):
                    st.caption(f"📁 Yadda saxlanılan fayllar: {result['artifacts'][0]}")
                
                db.add_agent_message("assistant", response_text)

elif menu == "Agent Radar (Security)":
    st.title("Agent Radar (Auto Governance)")
    st.write("Automatic Marketing OS fit map: world-class agent patterns are compared with our own modules, then the safest next build is ranked.")

    from gateway import agent_radar, hf_radar

    scan = agent_radar.load_latest_scan()
    if agent_radar.scan_is_stale(scan):
        with st.spinner("Running automatic governance scan..."):
            scan = agent_radar.run_marketing_os_scan()

    if st.button("Refresh automatic scan", use_container_width=True):
        with st.spinner("Refreshing automatic scan..."):
            scan = agent_radar.run_marketing_os_scan()

    summary = scan["system_fit_summary"]
    recommendation = scan["recommendation"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Overall fit", f"{summary['overall_rating']}/100")
    m2.metric("Avg fit", f"{summary['avg_fit_score']}/100")
    m3.metric("Avg risk", f"{summary['avg_risk_score']}/100")
    m4.metric("Top module", recommendation["phase"].split(" - ")[0])

    st.success(
        f"Best professional variant: {summary['best_variant']}. "
        f"Current recommendation: {recommendation['name']} -> {recommendation['decision']}."
    )
    st.caption(f"Generated: {scan['generated_at_iso']} | Report: {agent_radar.SCAN_REPORT_PATH}")

    st.markdown("### World comparison")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "module": item["name"],
                    "pattern": item["pattern"],
                    "fit_for_us": item["fit_for_us"],
                    "source": item["source"],
                }
                for item in scan["world_reference_modules"]
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Marketing OS opportunity map")
    rows = []
    for item in scan["ranked_candidates"]:
        candidate = item["candidate"]
        evaluation = item["evaluation"]
        rows.append(
            {
                "module": candidate["name"],
                "phase": item["phase"],
                "fit": item["fit_score"],
                "risk": evaluation["risk_score"],
                "verdict": evaluation["verdict"],
                "decision": item["decision"],
                "automation_job": item["automation_job"],
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("### Hugging Face opportunity radar")
    hf_scan = hf_radar.load_latest_scan()
    if hf_radar.scan_is_stale(hf_scan):
        with st.spinner("Running Hugging Face opportunity scan..."):
            hf_scan = hf_radar.run_hf_scan()

    if st.button("Refresh Hugging Face scan", key="refresh_hf_scan", use_container_width=True):
        with st.spinner("Refreshing Hugging Face scan..."):
            hf_scan = hf_radar.run_hf_scan()

    hf_summary = hf_scan["system_fit_summary"]
    hf_recommendation = hf_scan["recommendation"]
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("HF fit", f"{hf_summary['overall_rating']}/100")
    h2.metric("Avg fit", f"{hf_summary['avg_fit_score']}/100")
    h3.metric("Avg risk", f"{hf_summary['avg_risk_score']}/100")
    h4.metric("Top risk", hf_recommendation["verdict"])
    st.info(
        f"Best HF path: {hf_summary['best_variant']}. "
        f"Recommendation: {hf_recommendation['name']} -> {hf_recommendation['decision']}."
    )
    st.caption(f"Generated: {hf_scan['generated_at_iso']} | Report: {hf_radar.HF_REPORT_PATH}")

    hf_rows = []
    for item in hf_scan["ranked_opportunities"]:
        opportunity = item["opportunity"]
        evaluation = item["evaluation"]
        hf_rows.append(
            {
                "opportunity": opportunity["name"],
                "category": opportunity["category"],
                "fit": evaluation["fit_score"],
                "risk": evaluation["risk_score"],
                "privacy": evaluation["privacy_score"],
                "verdict": evaluation["verdict"],
                "decision": evaluation["decision"],
                "data_boundary": opportunity["data_boundary"],
            }
        )
    st.dataframe(pd.DataFrame(hf_rows), use_container_width=True, hide_index=True)

    with st.expander("Hugging Face controls and references", expanded=False):
        st.write(hf_scan["operating_principle"])
        for item in hf_scan["ranked_opportunities"][:3]:
            st.markdown(f"#### {item['opportunity']['name']}")
            for control in item["evaluation"]["required_controls"]:
                st.write(f"- {control}")
        st.markdown("#### Official references")
        for ref in hf_scan["official_references"]:
            st.write(f"- [{ref['name']}]({ref['url']})")

    st.markdown("### Next actions")
    for action in scan["next_actions"]:
        st.write(f"- {action}")

    with st.expander("Detailed ranked reasoning", expanded=False):
        for item in scan["ranked_candidates"]:
            st.markdown(f"#### {item['candidate']['name']}")
            st.write(item["why"])
            st.write("Integrations: " + ", ".join(item["integration_points"]))
            for control in item["evaluation"]["required_controls"]:
                st.write(f"- {control}")

    st.stop()

    def split_lines(value: str) -> list[str]:
        cleaned = value.replace("\n", ",")
        return [item.strip() for item in cleaned.split(",") if item.strip()]

    permission_options = [
        "network",
        "browser",
        "scraping",
        "file_read",
        "file_write",
        "database_read",
        "database_write",
        "customer_data",
        "pii",
        "social_posting",
        "email_send",
        "subprocess",
        "secrets",
        "admin",
        "local_network",
        "payment",
    ]

    with st.form("agent_radar_form"):
        name = st.text_input("Agent name")
        use_case = st.text_input("Use case")
        description = st.text_area("What it claims to do")
        source_url = st.text_input("Source URL")
        repository_url = st.text_input("Repository URL")
        owner = st.text_input("Owner / vendor")
        requested_permissions = st.multiselect("Requested permissions", permission_options)
        claims_text = st.text_area("Claims, one per line")
        evidence_text = st.text_area("Evidence, docs, demos, comments, one per line")
        notes = st.text_area("Internal notes")
        submitted = st.form_submit_button("Evaluate and store")

    if submitted:
        if not name.strip() or not use_case.strip():
            st.warning("Agent name and use case are required.")
        else:
            record = agent_radar.add_candidate(
                agent_radar.AgentCandidate(
                    name=name.strip(),
                    use_case=use_case.strip(),
                    description=description.strip(),
                    source_url=source_url.strip(),
                    repository_url=repository_url.strip(),
                    owner=owner.strip(),
                    requested_permissions=requested_permissions,
                    claims=split_lines(claims_text),
                    evidence=split_lines(evidence_text),
                    notes=notes.strip(),
                )
            )
            evaluation = record["evaluation"]
            st.success(f"Stored assessment {record['id']} with verdict: {evaluation['verdict']}")
            m1, m2, m3 = st.columns(3)
            m1.metric("Benefit", evaluation["benefit_score"])
            m2.metric("Risk", evaluation["risk_score"])
            m3.metric("Trust", evaluation["trust_score"])
            st.markdown("#### Required controls")
            for control in evaluation["required_controls"]:
                st.write(f"- {control}")
            st.markdown("#### Reasons")
            for reason in evaluation["reasons"]:
                st.write(f"- {reason}")

    st.markdown("### Recent assessments")
    records = agent_radar.load_records(limit=50)
    if records:
        rows = []
        for record in records:
            candidate = record["candidate"]
            evaluation = record["evaluation"]
            rows.append(
                {
                    "id": record["id"],
                    "name": candidate["name"],
                    "category": evaluation["category"],
                    "benefit": evaluation["benefit_score"],
                    "risk": evaluation["risk_score"],
                    "trust": evaluation["trust_score"],
                    "verdict": evaluation["verdict"],
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No agent candidates have been assessed yet.")

elif menu == "🎧 Customer Relations Center":
    st.title("🎧 Customer Relations Center")
    st.write("Müştəri şikayətlərinin, rəylərinin süni intellektlə canlı (Live) təsnifatı.")
    
    from gateway import database as db
    
    with st.expander("➕ Yeni Canlı Şikayət Daxil Et (Test)", expanded=False):
        with st.form("cx_form"):
            msg = st.text_area("Müştərinin mesajı:")
            ch = st.selectbox("Kanal:", ["instagram", "google_review", "facebook", "web_form"])
            if st.form_submit_button("Analiz Et və Bazaya Yaz"):
                with st.spinner("Gemini analiz edir..."):
                    res = triage.triage_message({"text": msg, "channel": ch})
                    db.add_cx_ticket(ch, msg, res.get("category"), res.get("sentiment"), res.get("severity"), res.get("recommended_reply"))
                    st.success("Triage tamamlandı və SQLite bazasına qeyd edildi!")

    m1, m2, m3 = st.columns(3)
    tickets = db.get_recent_cx_tickets()
    _neg = sum(1 for t in tickets if 'negative' in str(t).lower())
    m1.metric("Ümumi Müraciətlər (DB)", str(len(tickets)))
    m2.metric("Kritik SLA Riski", str(sum(1 for t in tickets if 'very_negative' in str(t).lower())), delta="Təcili", delta_color="inverse")
    m3.metric("Neqativ Hiss (Sentiment)", f"{_neg} / {len(tickets)}" if tickets else "0",
              "bazadakı qeydlərə görə", delta_color="off")
    
    st.markdown("### Son Triage qeydləri (Canlı İzləmə)")
    st.markdown("### CX Resolution Agent (Sandbox)")
    try:
        import resolution_agent

        plan = resolution_agent.build_plan_from_store(days=7, limit=8)
        p1, p2, p3 = st.columns(3)
        p1.metric("Draft queue", str(len(plan.get("draft_queue", []))))
        p2.metric("Send allowed", "No" if not plan.get("send_allowed") else "Yes")
        p3.metric("Approval", "Required" if plan.get("approval_required") else "Not required")
        st.info(plan.get("summary", "No CX recovery summary available."))

        drafts = plan.get("draft_queue", [])
        if drafts:
            rows = [
                {
                    "id": item.get("complaint_id"),
                    "priority": item.get("priority"),
                    "severity": item.get("severity"),
                    "category": item.get("category"),
                    "team": item.get("assigned_team"),
                    "overdue": item.get("overdue"),
                    "next_action": item.get("next_best_action"),
                }
                for item in drafts
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            with st.expander("Draft replies (human approval required)", expanded=False):
                for item in drafts[:5]:
                    st.markdown(f"**#{item.get('complaint_id')} - {item.get('priority')}**")
                    st.write(item.get("draft_reply"))
        else:
            st.success("No urgent CX recovery draft is needed right now.")

        with st.expander("Safety controls", expanded=False):
            for control in plan.get("safety_controls", []):
                st.write(f"- {control}")
    except Exception as exc:
        st.warning(f"CX Resolution Agent sandbox unavailable: {exc}")

    if tickets:
        st.dataframe(pd.DataFrame(tickets), use_container_width=True, hide_index=True)
    else:
        st.info("Məlumat bazası boşdur. Yuxarıdan yeni müraciət daxil edin.")
    st.caption("Məlumatlar real vaxt rejimində SQLite məlumat bazasından (gateway/database.py) oxunur.")

elif menu == "📈 Ads & Performans":
    st.title("📈 Ads Studio Analitikası")
    st.write("Meta üzərindən çəkilən real vaxt xərc və konversiya qrafikləri.")
    
    # Əsas KPI Metrikləri — real Meta datası (briefing kollektoru).
    import briefing_panel
    try:
        _, _ads = briefing_panel.get_data()
    except Exception as _e:
        _ads = {"status": "error", "detail": str(_e)}

    if _ads.get("status") == "ok" and _ads.get("mode") == "live":
        _mt = _ads["month_totals"]
        _cur = _ads.get("currency", "AZN")
        _camps = [c for c in (_ads.get("campaigns") or []) if float(c.get("spend") or 0) > 0]
        _leads = float(_mt.get("leads") or 0)
        _spend = float(_mt.get("spend") or 0)
        _cpl = (_spend / _leads) if _leads else None
        c1, c2, c3 = st.columns(3)
        c1.metric("Aktiv Kampaniyalar", str(len(_camps)))
        c2.metric(f"Ümumi Xərc (ay, {_cur})", briefing_panel._num(_spend, 2))
        c3.metric(f"Orta CPL ({_cur})", briefing_panel._num(_cpl, 2) if _cpl else "—",
                  f"{briefing_panel._num(_leads)} lead", delta_color="off")

        _daily = _ads.get("daily") or []
        if _daily:
            st.markdown("### Xərclərin Dinamikası (son günlər, canlı)")
            _df = pd.DataFrame(_daily)
            if {"date", "spend"}.issubset(_df.columns):
                st.area_chart(_df[["date", "spend"]].set_index("date"))
        st.caption(f"Mənbə: Meta Graph API · hesab {_ads.get('account')}")
    elif _ads.get("status") == "ok":
        st.info("Meta hesabı demo rejimdədir — canlı KPI üçün token/hesab qoşulmalıdır.")
    else:
        st.error(f"Meta datası əlçatmaz: `{_ads.get('detail', '?')}`")

    st.markdown("---")
    st.subheader("🤖 Süni İntellekt (Gemini) Analizi")
    st.write("Mövcud Meta kampaniyalarınızın effektivliyini anında yoxlayın.")
    
    if st.button("⚡ Meta Kampaniyalarını Analiz Et", type="primary", use_container_width=True):
        with st.spinner("Agent arxa planda ads-studio məlumatlarını oxuyur və analiz edir..."):
            from gateway.executor import execute
            from gateway.queue import Job
            
            # Agentə konkret vəzifə veririk
            task_prompt = "Ads-studio alətini işə sal, mövcud Meta kampaniyalarının (və ya test datalarının) vəziyyətini analiz et və mənə icraçı direktor üçün qısa, dəqiq xülasə ver."
            job = Job(
                id=int(time.time()), source="dashboard", chat_id=None,
                task=task_prompt, status="running", result=None, error=None,
                artifacts=[], created_at=time.time(), started_at=time.time(),
                finished_at=None
            )
            
            result = execute(job)
            st.session_state.ads_analysis_result = result["result"]
            st.success("Təhlil uğurla tamamlandı!")
            
    if "ads_analysis_result" in st.session_state:
        st.info(st.session_state.ads_analysis_result)

elif menu == "🛒 Price Hunter (Rəqabət)":
    st.title("🛒 Price Hunter · Rəqabət Monitorinqi")
    st.write("Rəqiblərin qiymət dəyişiklikləri və bazarın vəziyyəti barədə məlumat agenti.")
    
    st.error("**Xəbərdarlıq (Verdict):** Bakuelectronics.az-da 759.99 AZN-ə təklif olunan AirPods Pro 2 380-550 AZN-lik real bazar dəyərindən həddən artıq yüksəkdir!")
    st.markdown("""
    **Hesabat Detalları:**
    *   **Məhsul:** Apple AirPods Pro 2
    *   **Mənbə (Source coverage):** tap.az (21 təklif), bakuelectronics.az (5 təklif).
    *   **Qeyd:** Axtarışlar zamanı bloklanan mənbələr üçün Apify bypass aktivləşdirilməlidir.
    """)
    st.caption("Son hesabat: _run2.txt (airpods-pro-2-20260609)")

elif menu == "🎯 Influencer Hunter":
    st.title("🎯 Influencer Hunter · Creator Intelligence")
    st.write("Brief əsasında Azərbaycan Instagram bazarından uyğun influencer/blogger namizədlərini tapır, skorlayır və sübutlarla əsaslandırır.")

    c1, c2, c3 = st.columns(3)
    c1.metric("Shortlist çıxışı", "Top 3", "sübutlu")
    c2.metric("Skor rubriki", "0-10", "7 faktor")
    c3.metric("Backend", "8840", "FastAPI")

    st.link_button("Influencer Hunter panelini aç", "http://localhost:8840", use_container_width=True)
    st.code(r"influencer-hunter\run.bat", language="powershell")
    st.markdown("""
    **Nümunə brief:**
    `Xalq Sigorta üçün səyahət sığortası barədə emosional selling proposition yönümlü Instagram Reel canlandıracaq travel/lifestyle influencer lazımdır.`

    **Canlı Instagram dərinliyi üçün:** `.env` daxilində `APIFY_API_TOKEN` əlavə edin. Actor adları `IH_INSTAGRAM_*_ACTOR` dəyişənləri ilə override edilə bilər.
    """)

elif menu == "📚 Bilik Bazası (RAG)":
    st.title("📚 Xalq Insurance Digital OS · Korporativ Bilik Bazası")
    st.write("Sığorta şərtləri, daxili qaydalar və hesabatlar üzrə Vektor Axtarışı (Semantic Search).")
    
    from gateway import rag
    
    col1, col2 = st.columns(2)
    with col1.container(border=True):
        st.subheader("📥 Yeni Məlumat Yüklə")
        with st.form("rag_upload"):
            doc_title = st.text_input("Sənədin adı / Kateqoriya:")
            doc_text = st.text_area("Məzmun (Şərtlər, qərarlar, qaydalar...):", height=150)
            if st.form_submit_button("Vektorlaşdır və Yadda Saxla (Embed)"):
                if doc_text:
                    with st.spinner("Məlumat oxunur və riyazi vektorlara çevrilir..."):
                        try:
                            rag.add_document(doc_text, {"title": doc_title})
                            st.success(f"'{doc_title}' sistemə əlavə edildi və yadda saxlanıldı!")
                        except Exception as e:
                            st.error("⚠️ **Google API Limiti (429):** Çox sürətli sorğu göndərdiniz. Zəhmət olmasa təxminən 30-40 saniyə gözləyib təkrar düyməyə basın.")
                    
    with col2.container(border=True):
        st.subheader("🔍 Axtarış və Sual-Cavab")
        query = st.text_input("Sistemin yaddaşında axtar (məsələn: 'Kasko üçün françiza qaydası necədir?'):")
        if st.button("Sorğu Göndər", type="primary"):
            if query:
                with st.spinner("Vektor məlumat bazasında axtarılır..."):
                    try:
                        results = rag.search(query)
                        error_search = False
                    except Exception:
                        st.error("⚠️ **Limit:** Axtarış zamanı Google API limitinə düşdük. 30 saniyə gözləyin.")
                        results = []
                        error_search = True
                        
                    if not error_search:
                        if not results:
                            st.warning("Bu suala uyğun şirkət daxili məlumat tapılmadı.")
                        else:
                            st.success("Məlumat tapıldı! Agent cavab hazırlayır...")
                            context_str = "\n\n".join([f"Mənbə: {r['metadata'].get('title')}\nMəzmun: {r['text']}" for r in results])
                            
                            from config import GEMINI_API_KEY
                            from google import genai
                            client = genai.Client(api_key=GEMINI_API_KEY)
                            prompt = f"Aşağıdakı korporativ məlumatlara əsasən istifadəçinin sualına dəqiq, rəsmi və qısa cavab ver. Əgər məlumat yoxdursa, uydurma.\n\n{context_str}\n\nSual: {query}\nCavab:"
                            try:
                                resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                                st.markdown(f"**🤖 Xalq Insurance Digital OS Cavabı:**\n{resp.text}")
                            except Exception:
                                st.error("⚠️ **Limit Xətası:** Cavab hazırlanarkən API limitinə düşdük. Zəhmət olmasa bir az sonra təkrar sınayın.")
                            
                            with st.expander("Göstərilən cavabın mənbələrinə (Retrieved Context) bax"):
                                for r in results:
                                    st.info(f"**{r['metadata'].get('title')}** (Uyğunluq skoru: {r['score']:.2f})\n\n{r['text']}")

elif menu == "🎨 Kreativ Studio":
    # Merged creative module: old Social Studio (Imagen 3) + Atelier's brain
    # (brand-DNA 11-layer prompts + vision critique + A/B board), native here.
    import creative_studio
    creative_studio.render()
