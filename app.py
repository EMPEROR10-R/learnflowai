# app.py (Updated with CSV + Custom PDF)
import streamlit as st
import time
import bcrypt
import pyotp
import qrcode
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, BADGES
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet

# === PAGE CONFIG & HIDE BRANDING ===
st.set_page_config(page_title="LearnFlow AI", layout="wide", menu_items=None)
st.markdown("""
<style>
    #MainMenu, header, footer {visibility: hidden;}
    .stApp > div:last-child {display: none !important;}
    .block-container {padding-top: 2rem;}
</style>
""", unsafe_allow_html=True)

# === INIT ===
@st.cache_resource
def get_db(): return Database()

@st.cache_resource
def get_ai():
    key = st.secrets.get("GEMINI_API_KEY", "")
    if not key:
        st.error("GEMINI_API_KEY missing! Add in Secrets.")
        st.info("Get key: https://aistudio.google.com/app/apikey")
        st.stop()
    return AIEngine(key)

db = get_db()
ai = get_ai()

# === APPLY SETTINGS ===
def apply_settings():
    font = st.session_state.get("font_size", 16)
    theme = st.session_state.get("theme", "light")
    st.markdown(f"""
    <style>
    .stApp {{font-size:{font}px;}}
    .stApp {{background:{'#fff' if theme=='light' else '#1e1e1e'};color:{'#000' if theme=='light' else '#fff'};}}
    </style>
    """, unsafe_allow_html=True)

# === WELCOME / AUTH / LOGIN (same as before) ===
# ... [Keep your existing welcome(), auth(), login_user() functions] ...

# === ADMIN / SETTINGS (same) ===
# ... [Keep admin_control_center(), settings_page()] ...

# === MAIN APP ===
def main_app():
    apply_settings()

    # Sidebar
    st.sidebar.success(f"Welcome {st.session_state.user_name}!")
    if st.sidebar.button("My Account"): st.session_state.page = "dashboard"
    if st.sidebar.button("Settings"): st.session_state.page = "settings"
    if st.sidebar.button("Logout"): [del st.session_state[k] for k in list(st.session_state.keys())]; st.rerun()
    if st.session_state.is_admin and st.sidebar.button("Control Center"): st.session_state.page = "admin_center"

    # Routing
    if st.session_state.get("page") == "admin_center": admin_control_center(); return
    if st.session_state.get("page") == "settings": settings_page(); return

    # === DASHBOARD ===
    st.title("My Dashboard")
    if st.session_state.is_admin:
        st.success("**Unlimited Access**")
    elif st.session_state.is_premium:
        st.info("Premium User")

    # === CSV DATA ANALYSIS ===
    st.markdown("### Upload CSV for AI Analysis")
    csv_file = st.file_uploader("Upload CSV", type="csv")
    if csv_file:
        df = pd.read_csv(csv_file)
        st.write("**Data Preview**")
        st.dataframe(df.head())

        # Stats
        st.write("**Summary Statistics**")
        st.dataframe(df.describe())

        # Charts
        col1, col2 = st.columns(2)
        with col1:
            numeric_cols = df.select_dtypes(include='number').columns
            if len(numeric_cols) > 0:
                chart_col = st.selectbox("Select column for chart", numeric_cols)
                fig, ax = plt.subplots()
                df[chart_col].hist(ax=ax, bins=20, color='#00d4b1')
                ax.set_title(f"Distribution of {chart_col}")
                st.pyplot(fig)

        # AI Insights
        csv_text = df.to_csv(index=False)
        insight_query = st.text_input("Ask AI about this data:")
        if insight_query:
            with st.spinner("Analyzing data..."):
                prompt = f"CSV Data:\n{csv_text}\n\nQuestion: {insight_query}\nProvide insights, trends, and recommendations."
                resp = ai.generate_response(prompt, "You are a data analyst.")
            st.write("**AI Insights**")
            st.write(resp)

        # === Export CSV Analysis as PDF ===
        if st.button("Export CSV Analysis to PDF"):
            pdf_buffer = generate_csv_pdf(df, insight_query, resp if 'resp' in locals() else "")
            st.download_button(
                "Download PDF Report",
                data=pdf_buffer,
                file_name="csv_analysis_report.pdf",
                mime="application/pdf"
            )

    # === PDF UPLOAD (Existing) ===
    uploaded_pdf = st.file_uploader("Upload PDF for AI Analysis", type="pdf", key="pdf")
    if uploaded_pdf:
        pdf_bytes = uploaded_pdf.read()
        with st.spinner("Extracting text..."):
            pdf_text = ai.extract_text_from_pdf(pdf_bytes)
        st.text_area("PDF Text", pdf_text, height=200)
        pdf_query = st.text_input("Ask about PDF:")
        if pdf_query:
            resp = ai.generate_response(f"Context: {pdf_text}\nQuery: {pdf_query}", "PDF Analyst")
            st.write(resp)

    # === SUBJECT + CHAT/QUIZ ===
    subject = st.sidebar.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))
    mode = st.sidebar.radio("Mode", ["Chat", "Quiz"], horizontal=True)
    if mode == "Quiz":
        show_quiz_mode(subject)
    else:
        show_chat_mode(subject)

# === CUSTOM PDF GENERATOR (CSV + Quiz) ===
def generate_csv_pdf(df, question, ai_insight):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    # Header
    elements.append(Paragraph("LearnFlow AI - CSV Data Analysis Report", styles['Title']))
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph(f"Generated: {time.strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    elements.append(Paragraph(f"User: {st.session_state.user_name}", styles['Normal']))
    elements.append(Spacer(1, 0.3*inch))

    # Question
    if question:
        elements.append(Paragraph(f"<b>Question:</b> {question}", styles['Normal']))
        elements.append(Spacer(1, 0.2*inch))

    # AI Insight
    if ai_insight:
        elements.append(Paragraph("<b>AI Insights:</b>", styles['Normal']))
        for line in ai_insight.split('\n'):
            elements.append(Paragraph(line, styles['Normal']))
        elements.append(Spacer(1, 0.3*inch))

    # Data Table
    data = [df.columns.tolist()] + df.values.tolist()
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#00d4b1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]))
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer

# === QUIZ MODE (with PDF export) ===
def show_quiz_mode(subject):
    st.header(f"Quiz – {subject}")
    if st.button("Start 5-Question Quiz"):
        qs = ai.generate_mcq_questions(subject, 5)
        st.session_state.quiz = {"questions": qs, "answers": {}, "start": time.time()}
        st.rerun()

    if "quiz" in st.session_state:
        q = st.session_state.quiz
        for i, ques in enumerate(q["questions"]):
            with st.expander(f"Q{i+1}: {ques['question']}"):
                ans = st.radio("Choose", ques["options"], key=f"q{i}")
                q["answers"][i] = ans

        if st.button("Submit Quiz"):
            res = ai.grade_mcq(q["questions"], q["answers"])
            db.record_quiz_score(st.session_state.user_id, subject, res["correct"], res["total"])
            db.unlock_badge(st.session_state.user_id, "first_quiz")
            if res["percentage"] == 100:
                db.unlock_badge(st.session_state.user_id, "perfect_score")

            st.success(f"Score: {res['correct']}/{res['total']} ({res['percentage']}%)")
            for r in res["results"]:
                st.write(f"**Q:** {r['question']}")
                st.write(f"Your: {r['user_answer']} | Correct: {r['correct_answer']}")
                if not r["is_correct"]: st.info(r["feedback"])

            # === Export Quiz PDF ===
            if st.button("Export Quiz Report"):
                pdf_buffer = generate_quiz_pdf(res, subject)
                st.download_button(
                    "Download Quiz PDF",
                    data=pdf_buffer,
                    file_name=f"quiz_{subject}.pdf",
                    mime="application/pdf"
                )

            del st.session_state.quiz
            st.rerun()

def generate_quiz_pdf(result, subject):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("LearnFlow AI - Quiz Report", styles['Title']))
    elements.append(Paragraph(f"Subject: {subject}", styles['Normal']))
    elements.append(Paragraph(f"Score: {result['correct']}/{result['total']} ({result['percentage']}%)", styles['Normal']))
    elements.append(Paragraph(f"Date: {time.strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 0.3*inch))

    for r in result["results"]:
        elements.append(Paragraph(f"<b>Q:</b> {r['question']}", styles['Normal']))
        elements.append(Paragraph(f"Your: {r['user_answer']} | Correct: {r['correct_answer']}", styles['Normal']))
        if not r["is_correct"]:
            elements.append(Paragraph(f"Feedback: {r['feedback']}", styles['Italic']))
        elements.append(Spacer(1, 0.2*inch))

    doc.build(elements)
    buffer.seek(0)
    return buffer

# === CHAT MODE (unchanged) ===
def show_chat_mode(subject):
    st.header(subject)
    prompt = st.chat_input("Ask me anything…")
    if prompt:
        with st.chat_message("user"): st.write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                resp = ai.generate_response(f"{SUBJECT_PROMPTS[subject]}\nStudent: {prompt}", SUBJECT_PROMPTS[subject])
            st.write(resp)

# === ROUTER ===
if "page" not in st.session_state:
    st.session_state.page = "welcome"

if st.session_state.page == "welcome":
    welcome()
elif st.session_state.page == "auth":
    auth()
elif st.session_state.get("logged_in"):
    main_app()
else:
    st.session_state.page = "auth"
    st.rerun()
