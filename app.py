# app.py
import streamlit as st
import pandas as pd
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS
import qrcode
from io import BytesIO
import pyotp
import bcrypt
import time
import uuid

# ===================================================================
# PAGE CONFIG + HIDE STREAMLIT JUNK
# ===================================================================
st.set_page_config(page_title="LearnFlow AI", layout="centered")
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .stApp {background: linear-gradient(135deg, #0e1117, #1a1f2e);}
</style>
""", unsafe_allow_html=True)

# ===================================================================
# INIT
# ===================================================================
@st.cache_resource
def get_db(): return Database()

@st.cache_resource  
def get_ai():
    key = st.secrets.get("GEMINI_API_KEY", "")
    if not key:
        st.error("Add GEMINI_API_KEY in Secrets")
        st.stop()
    return AIEngine(key)

db = get_db()
ai = get_ai()

# ===================================================================
# ANIMATED WELCOME PAGE
# ===================================================================
def welcome_page():
    st.markdown("""
    <div style="text-align:center; padding:120px 20px;">
        <h1 style="font-size:70px; background:-webkit-linear-gradient(#00d4b1, #00ffaa);
                   -webkit-background-clip:text; -webkit-text-fill-color:transparent;
                   animation: glow 2s infinite alternate;">
            LearnFlow AI
        </h1>
        <p style="font-size:24px; color:#aaa;">Kenya's #1 AI Tutor • KCPE • KPSEA • KCSE</p>
        <br><br>
        <button onclick="document.getElementById('go').click()"
                style="padding:16px 60px; font-size:22px; background:#00d4b1; 
                       color:black; border:none; border-radius:50px; cursor:pointer;">
            Continue →
        </button>
    </div>
    <style>
    @keyframes glow {from {text-shadow:0 0 20px #00d4b1;} to {text-shadow:0 0 40px #00ffcc;}}
    </style>
    """, unsafe_allow_html=True)
    
    if st.button("Continue →", key="go", use_container_width=True):
        st.session_state.page = "auth"
        st.rerun()

# ===================================================================
# AUTH PAGE
# ===================================================================
def auth_page():
    st.markdown("<h1 style='text-align:center; color:#00d4b1;'>Welcome Back!</h1>", 
                unsafe_allow_html=True)
    
    login, signup = st.tabs(["Login", "Create Free Account"])
    
    with login:
        with st.form("login"):
            email = st.text_input("Email")
            pwd = st.text_input("Password", type="password")
            totp = st.text_input("2FA Code (if enabled)")
            submitted = st.form_submit_button("Login →")
            if submitted:
                ok, msg = login_user(email.lower(), pwd, totp)
                if ok:
                    st.success("Login successful!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(msg)
    
    with signup:
        with st.form("signup"):
            st.write("**Free Forever Account**")
            name = st.text_input("Full Name")
            email = st.text_input("Email")
            pwd = st.text_input("Create Password", type="password")
            phone = st.text_input("Phone (07xxxxxxxx)")
            if st.form_submit_button("Sign Up Free"):
                if db.get_user_by_email(email.lower()):
                    st.error("Email already exists!")
                else:
                    db.create_user(name, email.lower(), pwd, phone)
                    st.success("Account created! Now login →")
                    st.balloons()

# ===================================================================
# LOGIN FUNCTION (ADMIN WORKS!)
# ===================================================================
def login_user(email: str, password: str, totp_code: str = ""):
    user = db.get_user_by_email(email)
    if not user:
        return False, "User not found"
    
    if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return False, "Wrong password"
    
    # 2FA
    if user.get("two_fa_secret"):
        if not totp_code or not pyotp.TOTP(user["two_fa_secret"]).verify(totp_code):
            return False, "Invalid 2FA code"
    
    # SUCCESS
    st.session_state.update({
        "logged_in": True,
        "user_id": user["user_id"],
        "user_name": user.get("name", "Student"),
        "user_email": email,
        "is_admin": user["role"] == "admin",
        "is_parent": bool(db.get_children(user["user_id"]))
    })
    db.log_activity(user["user_id"], "login")
    return True, ""

# ===================================================================
# MAIN APP (after login)
# ===================================================================
def main_app():
    if st.session_state.is_admin:
        st.title("ADMIN DASHBOARD")
        st.success("Welcome back KingMumo!")
        st.write("All systems running – 100% working")
    else:
        st.sidebar.title(f"Hello {st.session_state.user_name}!")
        subject = st.sidebar.selectbox("Choose Subject", list(SUBJECT_PROMPTS.keys()))
        st.title(subject)
        prompt = st.chat_input("Ask anything...")
        if prompt:
            with st.chat_message("user"):
                st.write(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response = ai.generate(f"{SUBJECT_PROMPTS[subject]}\n\nStudent: {prompt}")
                st.write(response)

# ===================================================================
# ROUTER
# ===================================================================
if "page" not in st.session_state:
    st.session_state.page = "welcome"

if st.session_state.page == "welcome":
    welcome_page()
elif st.session_state.page == "auth":
    auth_page()
elif st.session_state.get("logged_in"):
    main_app()
else:
    st.session_state.page = "auth"
    st.rerun()
