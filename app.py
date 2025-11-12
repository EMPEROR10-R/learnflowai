# app.py
import streamlit as st
import os
import json
import time
import uuid
import pyotp
import qrcode
from io import BytesIO
import pandas as pd
import bcrypt
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES
from utils import Translator_Utils, EssayGrader, VoiceInputHelper
import streamlit.components.v1 as components

# ----------------------------------------------------------------------
# Page Config & CSS
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
    @keyframes pulse { 0%,100% {transform:scale(1);} 50% {transform:scale(1.05);} }
    @keyframes glow { 0%,100% {box-shadow:0 0 5px rgba(102,126,234,0.5);} 50% {box-shadow:0 0 20px rgba(102,126,234,0.8);} }
    @keyframes gradient-shift { 0% {background-position:0% 50%;} 50% {background-position:100% 50%;} 100% {background-position:0% 50%;} }
    .main-header {font-size:2.5rem; font-weight:bold;
        background:linear-gradient(135deg,#009E60 0%,#FFD700 50%,#CE1126 100%);
        background-size:200% 200%; -webkit-background-clip:text; -webkit-text-fill-color:transparent;
        text-align:center; margin-bottom:1rem;
        animation:fadeInDown 1s ease-out, gradient-shift 3s ease infinite;}
    .chat-message-user {background:#E8F5E9; padding:15px; border-radius:15px; margin:10px 0;
        border-left:4px solid #4CAF50;}
    .chat-message-ai {background:#E3F2FD; padding:15px; border-radius:15px; margin:10px 0;
        border-left:4px solid #2196F3;}
    .streak-badge {display:inline-block; padding:5px 15px;
        background:linear-gradient(135deg,#FF6B6B 0%,#FFE66D 100%); border-radius:20px;
        color:white; font-weight:bold; margin:5px; animation:pulse 2s ease-in-out infinite;}
    .premium-badge {background:linear-gradient(135deg,#FFD700 0%,#FFA500 100%);
        padding:3px 10px; border-radius:10px; color:white; font-size:.8rem; font-weight:bold;
        animation:glow 2s ease-in-out infinite;}
    .stButton>button {width:100%; transition:all .3s ease;}
    .stButton>button:hover {transform:translateY(-2px); box-shadow:0 5px 15px rgba(0,158,96,.4);}
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------------------
# Initialize Resources
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
    if not gemini_key:
        st.error("GEMINI_API_KEY missing in secrets!")
        st.stop()
    return AIEngine(gemini_key)

db = init_database()
ai_engine = init_ai_engine()
translator = init_translator()

# ----------------------------------------------------------------------
# Session State
# ----------------------------------------------------------------------
def init_session_state():
    defaults = {
        "chat_history": [],
        "current_subject": "Mathematics",
        "show_welcome": True,
        "logged_in": False,
        "is_admin": False,
        "user_id": None,
        "show_2fa_setup": False,
        "temp_2fa_secret": None,
        "show_premium": False,
        "user": None
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# ----------------------------------------------------------------------
# 2FA Helpers
# ----------------------------------------------------------------------
def generate_2fa_secret():
    return pyotp.random_base32()

def get_2fa_qr_code(email: str, secret: str) -> BytesIO:
    uri = pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="LearnFlow AI")
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf

# ----------------------------------------------------------------------
# Login / Signup Functions (FIXED: twofa_secret)
# ----------------------------------------------------------------------
def login_user(email: str, password: str, totp_code: str = ""):
    user = db.get_user_by_email(email)
    if not user:
        return False, "Invalid email or password.", None

    if "password_hash" not in user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return False, "Invalid email or password.", None

    # 2FA Check (FIXED: twofa_secret)
    if user.get("twofa_secret"):
        if not totp_code:
            return False, "2FA code required.", None
        if not pyotp.TOTP(user["twofa_secret"]).verify(totp_code):
            return False, "Invalid 2FA code.", None

    db.update_user_activity(user["user_id"])
    return True, "Login successful!", user

def signup_user(email: str, password: str):
    if db.get_user_by_email(email):
        return False, "Email already exists."
    user_id = db.create_user(email, password)
    if not user_id:
        return False, "Signup failed."
    return True, "Account created! Please log in."

# ----------------------------------------------------------------------
# Login / Signup Block
# ----------------------------------------------------------------------
def login_signup_block():
    if st.session_state.logged_in:
        return

    st.markdown("### Login or Sign Up")
    choice = st.radio("Choose", ["Login", "Sign Up"], horizontal=True, key="auth_choice")

    if choice == "Sign Up":
        email = st.text_input("Email", key="signup_email")
        pwd = st.text_input("Password", type="password", key="signup_pwd")
        if st.button("Create Account"):
            if not email or "@" not in email:
                st.error("Valid email required.")
            elif len(pwd) < 6:
                st.error("Password must be 6+ characters.")
            else:
                success, msg = signup_user(email, pwd)
                st.write(msg)
                if success:
                    st.success("Account created! Now log in.")

    else:
        email = st.text_input("Email", key="login_email")
        pwd = st.text_input("Password", type="password", key="login_pwd")
        totp = st.text_input("2FA Code (if enabled)", key="login_totp")
        if st.button("Login"):
            success, msg, user = login_user(email, pwd, totp)
            st.write(msg)
            if success:
                st.session_state.user = user
                st.session_state.user_id = user["user_id"]
                st.session_state.is_admin = user["role"] == "admin"
                st.session_state.logged_in = True
                st.rerun()

    # 2FA Setup (FIXED: twofa_secret)
    if st.session_state.logged_in and not st.session_state.show_2fa_setup:
        if not st.session_state.user.get("twofa_secret"):
            if st.button("Enable 2FA for Extra Security"):
                secret = generate_2fa_secret()
                db.enable_2fa(st.session_state.user_id, secret)
                st.session_state.temp_2fa_secret = secret
                st.session_state.show_2fa_setup = True
                st.rerun()

    if st.session_state.show_2fa_setup:
        st.markdown("### Set Up 2FA")
        secret = st.session_state.temp_2fa_secret
        qr_img = get_2fa_qr_code(st.session_state.user["email"], secret)
        st.image(qr_img, caption="Scan with Google Authenticator")
        st.code(secret, language=None)
        st.info("Enter the 6-digit code from your app.")
        code = st.text_input("Verification Code", max_chars=6)
        if st.button("Verify 2FA"):
            if pyotp.TOTP(secret).verify(code):
                st.success("2FA enabled!")
                st.session_state.show_2fa_setup = False
                del st.session_state.temp_2fa_secret
                st.rerun()
            else:
                st.error("Invalid code.")

    st.stop()

# ----------------------------------------------------------------------
# Streak & Limits
# ----------------------------------------------------------------------
def check_and_update_streak():
    streak = db.update_streak(st.session_state.user_id)
    if streak in [3, 7, 30]:
        db.add_badge(st.session_state.user_id, f"streak_{streak}")
    return streak

def check_premium_limits():
    is_premium = db.check_premium(st.session_state.user_id)
    if is_premium:
        return {"can_query": True, "can_upload_pdf": True, "queries_left": "Unlimited", "pdfs_left": "Unlimited", "is_premium": True}
    queries = db.get_daily_query_count(st.session_state.user_id)
    pdfs = db.get_pdf_count_today(st.session_state.user_id)
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
        limits = check_premium_limits()
        if limits["is_premium"]:
            st.markdown('<span class="premium-badge">PREMIUM</span>', unsafe_allow_html=True)
        streak = check_and_update_streak()
        st.markdown(f'<span class="streak-badge">{streak} Day Streak</span>', unsafe_allow_html=True)

        user = db.get_user(st.session_state.user_id)
        if user and user.get("badges"):
            badges = json.loads(user["badges"])
            if badges:
                st.write("**Badges:** " + " ".join([BADGES.get(b, b) for b in badges[:5]]))

        st.markdown("---")
        st.markdown("### Settings")
        subjects = list(SUBJECT_PROMPTS.keys())
        idx = subjects.index(st.session_state.current_subject) if st.session_state.current_subject in subjects else 0
        st.session_state.current_subject = st.selectbox("Subject", subjects, index=idx)

        if not limits["is_premium"]:
            st.metric("Queries Left", f"{limits['queries_left']}/10")
            st.metric("PDF Uploads Left", f"{limits['pdfs_left']}/1")
            if st.button("Upgrade to Premium", type="primary"):
                st.session_state.show_premium = True

        if st.button("Logout"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

# ----------------------------------------------------------------------
# Premium Tab
# ----------------------------------------------------------------------
def premium_tab():
    st.subheader("Upgrade to Premium – KES 500/month")
    st.info("Pay via M-Pesa and submit proof. Admin will activate your account.")

    phone = st.text_input("M-Pesa Phone (e.g. 07xx)", key="mpesa_phone")
    code = st.text_input("Transaction Code (e.g. ABC123XYZ)", key="mpesa_code")

    if st.button("Submit Proof"):
        if not phone or not code:
            st.error("Fill all fields.")
        else:
            db.add_manual_payment(st.session_state.user_id, phone, code)
            st.success("Submitted! Admin will verify within 24 hours.")

# ----------------------------------------------------------------------
# Admin Dashboard
# ----------------------------------------------------------------------
def admin_dashboard_tab():
    if not st.session_state.is_admin:
        st.error("Access denied.")
        return

    st.subheader("Pending M-Pesa Payments")
    payments = db.get_pending_manual_payments()
    if not payments:
        st.info("No pending payments.")
    else:
        for p in payments:
            with st.expander(f"{p['name']} – {p['mpesa_code']}"):
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Approve", key=f"approve_{p['id']}"):
                        db.approve_manual_payment(p["id"])
                        st.success("Approved!")
                        st.rerun()
                with c2:
                    if st.button("Reject", key=f"reject_{p['id']}"):
                        db.reject_manual_payment(p["id"])
                        st.error("Rejected.")
                        st.rerun()

# ----------------------------------------------------------------------
# Chat Interface
# ----------------------------------------------------------------------
def main_chat_interface():
    limits = check_premium_limits()
    st.markdown(f'<h1 class="main-header">{st.session_state.current_subject} Tutor</h1>', unsafe_allow_html=True)

    for msg in st.session_state.chat_history:
        cls = "chat-message-user" if msg["role"] == "user" else "chat-message-ai"
        role = "You" if msg["role"] == "user" else "AI Tutor"
        st.markdown(f'<div class="{cls}"><strong>{role}:</strong> {msg["content"]}</div>', unsafe_allow_html=True)

    question = st.text_area("Ask anything:", height=100, key="question_input")
    if st.button("Send", type="primary"):
        if not question.strip():
            return
        if not limits["can_query"]:
            st.error("Daily limit reached! Upgrade to Premium.")
            return

        st.session_state.chat_history.append({"role": "user", "content": question})
        with st.spinner("Thinking..."):
            prompt = get_enhanced_prompt(st.session_state.current_subject, question, "")
            response = ai_engine.generate_response(question, prompt)

        st.session_state.chat_history.append({"role": "assistant", "content": response})
        st.markdown(f'<div class="chat-message-ai"><strong>AI Tutor:</strong> {response}</div>', unsafe_allow_html=True)
        db.add_chat_history(st.session_state.user_id, st.session_state.current_subject, question, response)
        db.update_user_activity(st.session_state.user_id)
        st.rerun()

# ----------------------------------------------------------------------
# Main App
# ----------------------------------------------------------------------
def main():
    init_session_state()

    if st.session_state.show_welcome:
        st.markdown("""
        <div style="text-align:center; padding:40px; background:linear-gradient(135deg,#009E60,#FFD700); border-radius:20px; color:white;">
            <h1>LearnFlow AI</h1>
            <p>Your Kenyan AI Tutor</p>
            <p>KCPE • KPSEA • KJSEA • KCSE</p>
        </div>
        """, unsafe_allow_html=True)
        _, col, _ = st.columns([1,1,1])
        with col:
            if st.button("Start Learning!", type="primary", use_container_width=True):
                st.session_state.show_welcome = False
                st.rerun()
        return

    login_signup_block()
    sidebar_config()

    tabs = st.tabs(["Chat", "PDF", "Quiz", "Premium", "Parent"])
    if st.session_state.is_admin:
        with st.expander("Admin Panel"):
            admin_dashboard_tab()

    with tabs[0]:
        main_chat_interface()
    with tabs[1]:
        st.write("PDF Upload – Coming soon")
    with tabs[2]:
        st.write("Quiz – Coming soon")
    with tabs[3]:
        premium_tab()
    with tabs[4]:
        st.write("Parent Dashboard – Coming soon")

    st.caption("LearnFlow AI – KCPE • KPSEA • KJSEA • KCSE")

if __name__ == "__main__":
    main()
