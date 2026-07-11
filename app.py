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

# ARCHIVE. This used to be the whole system's portal; the standalone studios and
# the hub replaced it. 7 of its 10 modules were duplicates of live tools (and its
# Price Hunter was hardcoded demo text — a lie in the product), so they were cut
# on 2026-07-11. Only the 3 modules that still exist nowhere else remain, until
# each finds its home: Gündəlik Hesabat -> ads studio, Agent Radar -> panel,
# Bilik Bazası (RAG) -> its own service. Then this file goes away entirely.
st.set_page_config(
    page_title="Arxiv modulları",
    page_icon="🗄️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Sol Menyu (Sidebar)
st.sidebar.title("🗄️ Arxiv")
st.sidebar.caption("Köçürülməmiş 3 modul")
st.sidebar.divider()

MODULES = [
    "📋 Gündəlik Hesabat",
    "Agent Radar (Security)",
    "📚 Bilik Bazası (RAG)",
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
st.sidebar.warning(
    "Bu ARXİV alətidir. Gündəlik iş üçün hub-ı işlət — "
    "burada yalnız hələ öz yerinə köçürülməmiş 3 modul qalıb."
)

if menu == "📋 Gündəlik Hesabat":
    import briefing_panel
    briefing_panel.render()

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

