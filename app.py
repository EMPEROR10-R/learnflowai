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
from mpesa_auth import get_oauth_token, stk_push  # Import stk_push
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
    .admin-badge {background:linear-gradient(135deg,#c80000,#ff4d4d); padding:3px 10px; border-radius:10px; color:white; font-size:.8rem; font-weight:bold; animation:glow 2s ease-in-out infinite;}
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
# Premium Tab - FULLY REWRITTEN WITH STK PUSH
# ----------------------------------------------------------------------
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
        phone = st.text_input(
            "M-Pesa Phone Number",
            value="254712345678",
            help="Format: 2547XXXXXXXXX (no spaces or +)",
            key="mpesa_phone"
        )
    with col2:
        amount = st.number_input(
            "Amount (KES)",
            min_value=500,
            max_value=10000,
            value=500,
            step=100,
            key="mpesa_amount"
        )

    st.markdown("---")
    if st.button("Pay with M-Pesa", type="primary", use_container_width=True):
        if not phone.startswith("2547") or len(phone) != 12 or not phone.isdigit():
            st.error("Invalid phone! Use format: **254712345678**")
            return

        try:
            with st.spinner("Initiating M-Pesa STK Push..."):
                result = stk_push(
                    phone=phone,
                    amount=amount,
                    account_ref="LearnFlowAI",
                    desc="LearnFlow AI Premium Monthly"
                )

            if result.get("ResponseCode") == "0":
                checkout_id = result['CheckoutRequestID']
                st.success("STK Push sent successfully!")
                st.info(f"**Open your phone & approve the payment**")
                st.code(f"Checkout ID: {checkout_id}")
                st.markdown("""
                > **Sandbox Tip**: Enter PIN **1234** to simulate payment
                """)
                # Save pending payment
                db.record_pending_payment(st.session_state.user_id, phone, amount, checkout_id)
            else:
                st.error(f"M-Pesa Error: {result.get('errorMessage', 'Unknown error')}")

        except Exception as e:
            st.error(f"Payment failed: {str(e)}")
            st.info("Check your Daraja app credentials or internet connection.")

    st.markdown("---")
    st.caption("Powered by Safaricom Daraja API • Secure & Instant")

# ----------------------------------------------------------------------
# [Rest of your tabs unchanged]
# ----------------------------------------------------------------------
# ... [main_chat_interface, pdf_upload_tab, progress_dashboard_tab, etc. remain the same]

def main_chat_interface():
    db = init_database()
    limits = check_premium_limits(db)

    st.markdown(f'<h1 class="main-header">{st.session_state.current_subject} Tutor</h1>', unsafe_allow_html=True)

    for msg in st.session_state.chat_history:
        cls = "chat-message-user" if msg["role"] == "user" else "chat-message-ai"
        role = "You" if msg["role"] == "user" else "AI Tutor"
        st.markdown(f'<div class="{cls}"><strong>{role}:</strong> {msg["content"]}</div>', unsafe_allow_html=True)

    user_question = st.text_area(
        "Ask your question:",
        height=100, key="user_input",
        placeholder="e.g. Explain photosynthesis in simple terms…"
    )

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
            system_prompt = get_enhanced_prompt(
                st.session_state.current_subject,
                user_question,
                f"Previous messages: {len(st.session_state.chat_history)}"
            )
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

# ... [keep all other functions: pdf_upload_tab, exam_mode_tab, etc.]

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

    st.caption("LearnFlow AI – Built for Kenyan Students")

if __name__ == "__main__":
    main()
