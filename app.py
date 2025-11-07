# app.py
import streamlit as st
import os
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
import json
import time
import uuid
import smtplib
import random
import pandas as pd
from database import Database
from ai_engine import AIEngine
from utils import Translator_Utils, EssayGrader, VoiceInputHelper
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES
from stripe_premium import StripePremium, show_premium_upgrade_banner, show_premium_benefits
from mpesa_auth import stk_push
import streamlit.components.v1 as components

# ----------------------------------------------------------------------
# Page config & CSS
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="LearnFlow AI - Kenyan AI Tutor",
    page_icon="Kenya",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @keyframes fadeInDown { from {opacity:0; transform:translateY(-30px);} to {opacity:1; transform:translateY(0);} }
    @keyframes slideInLeft { from {opacity:0; transform:translateX(-50px);} to {opacity:1; transform:translateX(0);} }
    @keyframes slideInRight { from {opacity:0; transform:translateX(50px);} to {opacity:1; transform:translateX(0);} }
    @keyframes pulse { 0%,100% {transform:scale(1);} 50% {transform:scale(1.05);} }
    @keyframes glow { 0%,100% {box-shadow:0 0 5px rgba(102,126,234,0.5);} 50% {box-shadow:0 0 20px rgba(102,126,234,0.8);} }
    @keyframes gradient-shift { 0% {background-position:0% 50%;} 50% {background-position:100% 50%;} 100% {background-position:0% 50%; } }

    .main-header {font-size:2.5rem; font-weight:bold;
        background:linear-gradient(135deg,#009E60 0%,#FFD700 50%,#CE1126 100%);
        background-size:200% 200%; -webkit-background-clip:text; -webkit-text-fill-color:transparent;
        text-align:center; margin-bottom:1rem;
        animation:fadeInDown 1s ease-out, gradient-shift 3s ease infinite;}
    .chat-message-user {background:#E8F5E9; padding:15px; border-radius:15px; margin:10px 0;
        border-left:4px solid #4CAF50; animation:slideInRight .5s ease-out;}
    .chat-message-ai {background:#E3F2FD; padding:15px; border-radius:15px; margin:10px 0;
        border-left:4px solid #2196F3; animation:slideInLeft .5s ease-out;}
    .streak-badge {display:inline-block; padding:5px 15px;
        background:linear-gradient(135deg,#FF6B6B 0%,#FFE66D 100%); border-radius:20px;
        color:white; font-weight:bold; margin:5px; animation:pulse 2s ease-in-out infinite;}
    .premium-badge {background:linear-gradient(135deg,#FFD700 0%,#FFA500 0%); padding:3px 10px; border-radius:10px; color:white; font-size:.8rem; font-weight:bold; animation:glow 2s ease-in-out infinite;}
    .admin-badge {background:linear-gradient(135deg,#c80000,#ff4d4d); padding:3px 10px; border-radius:10px; color:white; font-size:.8rem; font-weight:bold; animation:glow Dt 2s ease-in-out infinite;}
    .stButton>button {width:100%; transition:all .3s ease;}
    .stButton>button:hover {transform:translateY(-2px); box-shadow:0 5px 15px rgba(0,158,96,.4);}
    .welcome-animation {animation:fadeInDown 1.2s ease-out;}
    .metric-card {animation:fadeInDown .8s ease-out;}
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------------------
# Cached Resources
# ----------------------------------------------------------------------
@st.cache_resource
def init_database() -> Database:
    return Database()

@st.cache_resource
def init_translator() -> Translator_Utils:
    return Translator_Utils()

@st.cache_resource
def init_ai_engine() -> AIEngine:
    gemini_key = st.secrets.get("GEMINI_API_KEY", "")
    hf_key = st.secrets.get("HF_API_KEY", "")
    return AIEngine(gemini_key, hf_key)

ai_engine = init_ai_engine()

# ----------------------------------------------------------------------
# Session State
# ----------------------------------------------------------------------
def init_session_state():
    defaults = {
        "chat_history": [],
        "current_subject": "Mathematics",
        "language": "en",
        "show_voice_button": True,
        "show_welcome": True,
        "logged_in": False,
        "is_admin": False,
        "user_id": None,
        "show_premium": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if "user_id" not in st.session_state or not st.session_state.user_id:
        db = init_database()
        st.session_state.user_id = db.create_user()

# ----------------------------------------------------------------------
# Streak & Limits
# ----------------------------------------------------------------------
def check_and_update_streak():
    db = init_database()
    streak = db.update_streak(st.session_state.user_id)
    if streak == 3:   db.add_badge(st.session_state.user_id, "streak_3")
    elif streak == 7: db.add_badge(st.session_state.user_id, "streak_7")
    elif streak == 30:db.add_badge(st.session_state.user_id, "streak_30")
    return streak

def check_premium_limits(db: Database) -> dict:
    if st.session_state.is_admin:
        return {"can_query": True, "can_upload_pdf": True, "queries_left": "∞", "pdfs_left": "∞", "is_premium": True}

    is_premium = db.check_premium(st.session_state.user_id)
    if is_premium:
        return {"can_query": True, "can_upload_pdf": True, "queries_left": "∞", "pdfs_left": "∞", "is_premium": True}

    queries = db.get_daily_query_count(st.session_state.user_id)
    pdfs    = db.get_pdf_count_today(st.session_state.user_id)
    return {
        "can_query": queries < 10,
        "can_upload_pdf": pdfs < 1,
        "queries_left": max(0, 10 - queries),
        "pdfs_left": max(0, 1 - pdfs),
        "is_premium": False,
    }

# ----------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------
def sidebar_config():
    with st.sidebar:
        st.markdown('<p class="main-header">LearnFlow AI</p>', unsafe_allow_html=True)
        db = init_database()
        limits = check_premium_limits(db)

        if limits["is_premium"]:
            st.markdown('<span class="premium-badge">PREMIUM</span>', unsafe_allow_html=True)
        if st.session_state.is_admin:
            st.markdown('<span class="admin-badge">ADMIN</span>', unsafe_allow_html=True)

        streak = check_and_update_streak()
        st.markdown(f'<span class="streak-badge">{streak} Day Streak</span>', unsafe_allow_html=True)

        user = db.get_user(st.session_state.user_id)
        if user and user.get("badges"):
            badges = json.loads(user["badges"])
            if badges:
                st.write("**Badges:**")
                st.write(" ".join([BADGES.get(b, b) for b in badges[:5]]))

        st.markdown("---")
        st.markdown("### Settings")

        subjects = list(SUBJECT_PROMPTS.keys())
        idx = subjects.index(st.session_state.current_subject) if st.session_state.current_subject in subjects else 0
        st.session_state.current_subject = st.selectbox("Choose subject", subjects, index=idx)

        translator = init_translator()
        lang_map = {v: k for k, v in translator.supported_languages.items()}
        sel_lang = st.selectbox("Interface Language", list(lang_map.keys()), index=0)
        st.session_state.language = lang_map[sel_lang]

        st.markdown("---")
        if not limits["is_premium"] and not st.session_state.is_admin:
            st.markdown("### Daily Limits (Free)")
            st.metric("AI Queries Left", f"{limits['queries_left']}/10")
            st.metric("PDF Uploads Left", f"{limits['pdfs_left']}/1")
            if st.button("Upgrade to Premium", type="primary"):
                st.session_state.show_premium = True

        st.markdown("---")
        st.caption("KCPE • KPSEA • KJSEA • KCSE Ready")

# ----------------------------------------------------------------------
# WELCOME ANIMATION - FIXED!
# ----------------------------------------------------------------------
def show_welcome_animation():
    if st.session_state.get("show_welcome", True):
        st.markdown("""
        <div class="welcome-animation" style="background:linear-gradient(135deg,#009E60,#FFD700); padding:40px; border-radius:20px; text-align:center; color:white; margin:20px 0; box-shadow:0 10px 30px rgba(0,0,0,.2);">
            <h1 style="font-size:3rem; margin:0;">LearnFlow AI</h1>
            <p style="font-size:1.5rem;">Your Kenyan AI Tutor</p>
            <p>KCPE • KPSEA • KJSEA • KCSE Ready</p>
        </div>
        """, unsafe_allow_html=True)
        _, col, _ = st.columns([1, 1, 1])
        with col:
            if st.button("Start Learning!", type="primary", use_container_width=True):
                st.session_state.show_welcome = False
                st.rerun()

# ----------------------------------------------------------------------
# Login / Signup
# ----------------------------------------------------------------------
def login_signup_block():
    if st.session_state.logged_in:
        return

    st.markdown("### Login or Sign Up")
    choice = st.radio("Choose", ["Login", "Sign Up"], horizontal=True)
    db = init_database()

    if choice == "Sign Up":
        email = st.text_input("Email")
        pwd   = st.text_input("Password", type="password")
        if st.button("Create Account"):
            if not email or "@" not in email:
                st.error("Valid email required.")
            elif not pwd:
                st.error("Password required.")
            elif db.get_user_by_email(email):
                st.error("Email taken.")
            else:
                uid = db.create_user(email, pwd)
                st.session_state.user_id = uid
                st.session_state.logged_in = True
                st.session_state.is_admin = db.is_admin(uid)
                st.success("Account created!")
                st.rerun()
    else:
        email = st.text_input("Email", key="login_email")
        pwd   = st.text_input("Password", type="password", key="login_pwd")
        if st.button("活動"):
            uid = db.login_user(email, pwd)
            if uid:
                st.session_state.user_id = uid
                st.session_state.logged_in = True
                st.session_state.is_admin = db.is_admin(uid)
                st.success("Logged in!")
                st.rerun()
            else:
                st.error("Wrong credentials.")

    st.stop()

# ----------------------------------------------------------------------
# Tabs
# ----------------------------------------------------------------------
def main_chat_interface():
    db = init_database()
    limits = check_premium_limits(db)

    st.markdown(f'<h1 class="main-header">{st.session_state.current_subject} Tutor</h1>', unsafe_allow_html=True)

    for msg in st.session_state.chat_history:
        cls = "chat-message-user" if msg["role"] == "user" else "chat-message-ai"
        role = "You" if msg["role"] == "user" else "AI Tutor"
        st.markdown(f'<div class="{cls}"><strong>{role}:</strong> {msg["content"]}</div>', unsafe_allow_html=True)

    user_question = st.text_area("Ask your question:", height=100, key="user_input", placeholder="e.g. Explain photosynthesis…")
    col_v1, _ = st.columns([1, 4])
    with col_v1:
        if st.button("Voice"):
            components.html(VoiceInputHelper.get_voice_input_html(), height=120)

    if st.button("Send", type="primary"):
        if not user_question.strip():
            st.warning("Please enter a question.")
            return
        if not limits["can_query"]:
            st.error("Daily query limit reached!")
            show_premium_upgrade_banner()
            return

        st.session_state.chat_history.append({"role": "user", "content": user_question})

        with st.spinner("Thinking…"):
            system_prompt = get_enhanced_prompt(st.session_state.current_subject, user_question, f"Previous: {len(st.session_state.chat_history)}")
            response = ""
            placeholder = st.empty()
            for chunk in ai_engine.stream_response(user_question, system_prompt):
                response += chunk
                placeholder.markdown(f'<div class="chat-message-ai"><strong>AI Tutor:</strong> {response}</div>', unsafe_allow_html=True)

        st.session_state.chat_history.append({"role": "assistant", "content": response})
        db.add_chat_history(st.session_state.user_id, st.session_state.current_subject, user_question, response)
        db.update_user_activity(st.session_state.user_id)

        if len(st.session_state.chat_history) == 2:
            db.add_badge(st.session_state.user_id, "first_question")
            st.balloons()

        st.rerun()

def pdf_upload_tab():
    db = init_database()
    limits = check_premium_limits(db)

    st.markdown("### Upload Notes / PDFs")
    if not limits["can_upload_pdf"]:
        st.warning("Daily PDF limit reached!")
        show_premium_upgrade_banner()
        return

    uploaded = st.file_uploader("Choose a PDF", type=["pdf"])
    if uploaded:
        with st.spinner("Extracting text…"):
            txt = ai_engine.extract_text_from_pdf(uploaded.read())

        st.success(f"Extracted {len(txt)} characters")
        with st.expander("Raw Text"):
            st.code(txt[:2000] + ("..." if len(txt) > 2000 else ""))

        db.add_pdf_upload(st.session_state.user_id, uploaded.name)
        db.add_badge(st.session_state.user_id, "pdf_explorer")

        q = st.text_area("Ask about this PDF", placeholder="e.g. What is the main topic?")
        if st.button("Ask"):
            if not q.strip():
                st.warning("Please ask a question.")
                return
            with st.spinner("Analyzing…"):
                prompt = f"Document:\n{txt[:3000]}\n\nQuestion: {q}"
                resp = ai_engine.generate_response(prompt, "Answer in 1-3 short sentences.")
                st.markdown(f'<div class="chat-message-ai"><strong>AI Tutor:</strong> {resp}</div>', unsafe_allow_html=True)
                db.add_chat_history(st.session_state.user_id, "PDF", q, resp)

def progress_dashboard_tab():
    db = init_database()
    user = db.get_user(st.session_state.user_id)
    if not user:
        st.info("No data yet.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Questions", user.get("total_queries", 0))
    c2.metric("Streak", f"{user.get('streak_days', 0)} days")
    badges = json.loads(user.get("badges", "[]"))
    c3.metric("Badges", len(badges))
    c4.metric("Status", "Admin" if st.session_state.is_admin else ("Premium" if db.check_premium(st.session_state.user_id) else "Free"))

def exam_mode_tab():
    db = init_database()
    limits = check_premium_limits(db)

    st.markdown("### Exam Prep Mode")
    exam = st.selectbox("Select Exam", list(EXAM_TYPES.keys()), format_func=lambda x: f"{x} – {EXAM_TYPES[x]['description']}")
    info = EXAM_TYPES[exam]
    st.info(info["description"])

    subject = st.selectbox("Subject", info["subjects"])
    num_questions = st.slider("Number of Questions", 1, 10, 5)

    if st.button("Generate Practice Questions", type="primary"):
        if not limits["can_query"]:
            st.error("Query limit reached.")
            show_premium_upgrade_banner()
            return

        with st.spinner("Generating…"):
            prompt = f"Generate {num_questions} {exam} practice questions in {subject}. Include 4 options (A-D), one correct answer, and a brief explanation. Use Kenyan curriculum style."
            resp = ai_engine.generate_response(prompt, "You are an expert Kenyan exam generator. Output clean markdown.")
            st.markdown(resp)
            db.add_chat_history(st.session_state.user_id, f"{exam} Practice", f"Generate {num_questions} Qs in {subject}", resp)

    st.markdown("### Self-Score")
    score = st.slider("How many did you get right?", 0, num_questions, 0, key="score_slider")
    if st.button("Submit Score"):
        pct = score / num_questions * 100
        if pct >= 80:
            st.success(f"**{pct:.0f}% – Excellent!**")
            db.add_badge(st.session_state.user_id, "quiz_ace")
            st.balloons()
        elif pct >= 60:
            st.info(f"**{pct:.0f}% – Good!** Keep practicing.")
        else:
            st.warning(f"**{pct:.0f}% – Review {subject}**")
        db.add_quiz_result(st.session_state.user_id, subject, exam, score, num_questions)

def essay_grader_tab():
    st.markdown("### AI Essay Grader")
    essay = st.text_area("Paste your essay here", height=300)
    if st.button("Grade Essay"):
        if not essay.strip():
            st.warning("Please enter your essay.")
            return
        with st.spinner("Grading…"):
            grader = EssayGrader()
            res = grader.grade_essay(essay)
            st.markdown(f"**Score:** {res['total_score']}/100 – {res['overall']}")
            for cat, sc in res["breakdown"].items():
                st.write(f"- **{cat.title()}**: {sc}/100")
            st.write("**Stats**")
            col1, col2, col3 = st.columns(3)
            col1.metric("Words", res["stats"]["word_count"])
            col2.metric("Sentences", res["stats"]["sentence_count"])
            col3.metric("Paragraphs", res["stats"]["paragraph_count"])

def premium_tab():
    st.markdown("### Premium Plan")
    show_premium_benefits()
    db = init_database()

    if db.check_premium(st.session_state.user_id):
        st.success("You are already a Premium member!")
        st.balloons()
        return

    st.markdown("**KES 500 / month** – Unlimited AI, PDFs, Exams, Voice & More!")

    col1, col2 = st.columns(2)
    with col1:
        phone = st.text_input("M-Pesa Phone", value="254712345678", key="mpesa_phone")
    with col2:
        amount = st.number_input("Amount (KES)", value=500, min_value=500, step=100)

    if st.button("Pay with M-Pesa", type="primary", use_container_width=True):
        if not phone.startswith("2547") or len(phone) != 12 or not phone.isdigit():
            st.error("Invalid phone! Use format: **254712345678**")
            return

        try:
            with st.spinner("Sending STK Push..."):
                result = stk_push(phone=phone, amount=amount)

            if result.get("ResponseCode") == "0":
                checkout_id = result["CheckoutRequestID"]
                db.record_pending_payment(st.session_state.user_id, phone, amount, checkout_id)
                st.success("STK Push sent! Check your phone")
                st.code(f"ID: {checkout_id}")
                st.info("Enter PIN **1234** in sandbox")
                st.balloons()

                st.markdown("""
                <script>
                    setTimeout(() => { window.parent.location.reload(); }, 20000);
                </script>
                """, unsafe_allow_html=True)
                st.info("Auto-refresh in 20 seconds...")
            else:
                st.error(f"M-Pesa Error: {result.get('errorMessage', 'Unknown')}")

        except Exception as e:
            st.error(f"Payment failed: {str(e)}")

def admin_dashboard_tab():
    if not st.session_state.is_admin:
        st.error("Access denied.")
        return

    st.markdown("## Admin Dashboard")
    db = init_database()
    users = db.get_all_users()
    df = pd.DataFrame(users)
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No users yet.")

    if users:
        selected_uid = st.selectbox("Select user", df["user_id"], format_func=lambda x: next(u["email"] for u in users if u["user_id"] == x))
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Toggle Premium"):
                db.toggle_premium(selected_uid)
                st.success("Toggled.")
                st.rerun()
        with col2:
            if st.button("Delete User", type="secondary"):
                if st.session_state.user_id == selected_uid:
                    st.error("Cannot delete self.")
                else:
                    db.delete_user(selected_uid)
                    st.success("Deleted.")
                    st.rerun()

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    init_session_state()

    qp = st.query_params
    if "success" in qp:
        st.success("Payment succeeded!")
        st.balloons()
    if "cancel" in qp:
        st.warning("Payment cancelled.")

    if st.session_state.show_welcome:
        show_welcome_animation()
        return

    login_signup_block()
    sidebar_config()

    tab_names = ["Chat Tutor", "PDF Upload", "Progress", "Exam Prep", "Essay Grader", "Premium"]
    if st.session_state.is_admin:
        tab_names.append("Admin Dashboard")

    tabs = st.tabs(tab_names)

    with tabs[0]: main_chat_interface()
    with tabs[1]: pdf_upload_tab()
    with tabs[2]: progress_dashboard_tab()
    with tabs[3]: exam_mode_tab()
    with tabs[4]: essay_grader_tab()
    with tabs[5]: premium_tab()
    if st.session_state.is_admin and len(tabs) > 6:
        with tabs[6]: admin_dashboard_tab()

    st.caption("LearnFlow AI – KCPE • KPSEA • KJSEA • KCSE")

if __name__ == "__main__":
    main()
