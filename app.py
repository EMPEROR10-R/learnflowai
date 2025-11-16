# app.py
import streamlit as st
import bcrypt
import json
import pandas as pd
from datetime import datetime
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES

st.set_page_config(page_title="LearnFlow AI", page_icon="KE", layout="wide")

try:
    db = Database()
    ai_engine = AIEngine(st.secrets.get("GEMINI_API_KEY", ""))
except Exception as e:
    st.error(f"INIT FAILED: {e}")
    st.stop()

def init_session():
    defaults = {
        "logged_in": False, "user_id": None, "is_admin": False, "user": None,
        "show_welcome": True, "chat_history": [], "current_subject": "Mathematics",
        "pdf_text": "", "current_tab": "Chat Tutor",
        "exam_questions": None, "user_answers": {}
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

def get_user_tier():
    if st.session_state.is_admin: return "admin"
    user = db.get_user(st.session_state.user_id)
    if not user: return "basic"
    if user.get("is_premium") and db.check_premium_validity(st.session_state.user_id):
        return "premium"
    return "basic"

def enforce_access():
    tier = get_user_tier()
    tab = st.session_state.current_tab
    if tier == "basic" and tab not in ["Chat Tutor", "Settings"]:
        st.warning("Upgrade to Premium to access this feature.")
        st.stop()
    if tier == "basic":
        if tab == "Chat Tutor" and not db.can_ask_question(st.session_state.user_id):
            st.error("Daily limit: 10 questions. Upgrade to Premium!")
            st.stop()
        if tab == "PDF Q&A" and not db.can_upload_pdf(st.session_state.user_id):
            st.error("Daily limit: 3 PDF uploads. Upgrade to Premium!")
            st.stop()

def welcome_screen():
    st.markdown('<div style="background:linear-gradient(135deg,#009E60,#FFD700);padding:60px;border-radius:20px;text-align:center;color:white">'
                '<h1>LearnFlow AI</h1><p>Your Kenyan AI Tutor</p><p>KCPE • KPSEA • KJSEA • KCSE • Python</p></div>', unsafe_allow_html=True)
    _, c, _ = st.columns([1,1,1])
    with c:
        if st.button("Start Learning!", type="primary", use_container_width=True):
            st.session_state.show_welcome = False
            st.rerun()

def login_block():
    if st.session_state.logged_in:
        return

    st.markdown("### Login / Sign Up")
    choice = st.radio("Action", ["Login", "Sign Up"], horizontal=True, label_visibility="collapsed")
    email = st.text_input("Email", key=f"{choice.lower()}_email")
    pwd = st.text_input("Password", type="password", key=f"{choice.lower()}_pwd")
    totp = st.text_input("2FA Code (if enabled)", key="totp") if choice == "Login" else ""

    if st.button(choice, type="primary"):
        if len(pwd) < 6:
            st.error("Password must be at least 6 characters.")
            return

        if choice == "Sign Up":
            uid = db.create_user(email, pwd)
            if uid:
                st.success("Account created! Please log in.")
            else:
                st.error("Email already exists.")
            return

        # LOGIN
        user = db.get_user_by_email(email)
        if not user:
            st.error("Invalid email or password.")
            return

        # FIX: Correct bcrypt comparison
        stored_hash = user["password_hash"]
        if isinstance(stored_hash, str):
            stored_hash = stored_hash.encode('utf-8')
        if not bcrypt.checkpw(pwd.encode('utf-8'), stored_hash):
            st.error("Invalid email or password.")
            return

        # 2FA (safe)
        try:
            if db.is_2fa_enabled(user["user_id"]) and not db.verify_2fa_code(user["user_id"], totp):
                st.error("Invalid 2FA code.")
                return
        except AttributeError:
            pass

        db.update_user_activity(user["user_id"])
        st.session_state.update({
            "logged_in": True,
            "user_id": user["user_id"],
            "is_admin": user["role"] == "admin",
            "user": user
        })
        st.success("Login successful!")
        st.rerun()

def sidebar():
    with st.sidebar:
        st.markdown("## LearnFlow AI")
        tier = get_user_tier()
        st.markdown(f"**Tier:** {tier.upper()}")
        if tier == "basic": st.warning("10 Qs/day | 3 PDFs/day")
        user = db.get_user(st.session_state.user_id) or {}
        streak = db.update_streak(st.session_state.user_id)
        st.markdown(f"**Streak:** {streak} days")
        st.session_state.current_subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()), key="subj")
        badges_raw = user.get("badges", "[]")
        try: badges = json.loads(badges_raw) if isinstance(badges_raw, str) else badges_raw
        except: badges = []
        for b in badges[:5]: st.markdown(f"{BADGES.get(b, b)}")
        st.markdown("### Leaderboard")
        lb = db.get_leaderboard("exam")[:3]
        for i, e in enumerate(lb): st.markdown(f"**{i+1}.** {e['email']} – {e['score']:.0f}")

# [Rest of tabs: chat_tab, pdf_tab, exam_tab, etc. – unchanged]
# ... (same as before)

def main():
    try:
        init_session()
        if st.session_state.show_welcome: welcome_screen(); return
        login_block()
        if not st.session_state.logged_in: st.info("Log in."); return
        sidebar()
        enforce_access()
        base_tabs = ["Chat Tutor", "Settings"]
        premium_tabs = ["PDF Q&A", "Exam Prep", "Essay Grader"]
        tabs = base_tabs.copy()
        tier = get_user_tier()
        if tier in ["premium", "admin"]:
            tabs.extend(premium_tabs)
        if tier == "basic":
            tabs.append("Premium")
        if st.session_state.is_admin:
            tabs.append("Admin Control Centre")
        tab_objs = st.tabs(tabs)
        with tab_objs[0]: chat_tab()
        if "Settings" in tabs:
            with tab_objs[tabs.index("Settings")]: settings_tab()
        if "PDF Q&A" in tabs:
            with tab_objs[tabs.index("PDF Q&A")]: pdf_tab()
        if "Exam Prep" in tabs:
            with tab_objs[tabs.index("Exam Prep")]: exam_tab()
        if "Essay Grader" in tabs:
            with tab_objs[tabs.index("Essay Grader")]: essay_tab()
        if "Premium" in tabs:
            with tab_objs[tabs.index("Premium")]: premium_tab()
        if "Admin Control Centre" in tabs:
            with tab_objs[tabs.index("Admin Control Centre")]: admin_dashboard()
    except Exception as e:
        st.error(f"CRASH: {e}")

if __name__ == "__main__":
    main()
