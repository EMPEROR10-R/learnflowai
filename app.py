# app.py
import streamlit as st
import os
from datetime import datetime, timedelta
import pandas as pd
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, EXAM_TYPES, get_enhanced_prompt, get_quiz_prompt
import qrcode
from io import BytesIO
import pyotp
import bcrypt

# ----------------------------------------------------------------------
# Page config
# ----------------------------------------------------------------------
st.set_page_config(page_title="LearnFlow AI", layout="wide", initial_sidebar_state="expanded")

# ----------------------------------------------------------------------
# Resources
# ----------------------------------------------------------------------
@st.cache_resource
def init_database() -> Database:
    return Database()

@st.cache_resource
def init_ai_engine() -> AIEngine:
    gemini_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
    if not gemini_key:
        st.error("GEMINI_API_KEY not found! Add it to Secrets or .env")
        st.stop()
    return AIEngine(gemini_key)

db = init_database()
ai_engine = init_ai_engine()

# ----------------------------------------------------------------------
# Session
# ----------------------------------------------------------------------
def init_session_state():
    defaults = {
        "logged_in": False, "is_admin": False, "user_id": None, "user_name": "", "user_email": "",
        "is_parent": False, "children": [], "manual_approved": False
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# ----------------------------------------------------------------------
# Login with 2FA
# ----------------------------------------------------------------------
def login_user(email: str, password: str, totp_code: str = ""):
    user = db.get_user_by_email(email.lower())
    if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return False, "Invalid email or password.", None

    if db.is_2fa_enabled(user["user_id"]):
        if not totp_code:
            return False, "2FA code required.", "2fa_needed"
        if not db.verify_2fa_code(user["user_id"], totp_code):
            return False, "Invalid 2FA code.", None

    st.session_state.update({
        "user_id": user["user_id"], "user_name": user.get("name", ""), "user_email": email.lower(),
        "is_admin": user["role"] == "admin", "logged_in": True,
        "is_parent": bool(db.get_children(user["user_id"]))
    })
    db.update_user_activity(user["user_id"])
    db.log_activity(user["user_id"], "login")
    return True, "Logged in successfully!", None

# ----------------------------------------------------------------------
# Settings Tab
# ----------------------------------------------------------------------
def settings_tab():
    st.header("Settings")
    user_id = st.session_state.user_id

    # 2FA
    st.subheader("Two-Factor Authentication")
    if db.is_2fa_enabled(user_id):
        st.success("2FA is Enabled")
        if st.button("Disable 2FA"):
            db.generate_2fa_secret(user_id, disable=True)
            st.success("2FA disabled")
            st.rerun()
    else:
        st.info("Enable 2FA for extra security")
        if st.button("Enable 2FA"):
            secret = db.generate_2fa_secret(user_id)
            uri = pyotp.TOTP(secret).provisioning_uri(name=st.session_state.user_email, issuer_name="LearnFlow AI")
            qr = qrcode.make(uri)
            buf = BytesIO()
            qr.save(buf, format="PNG")
            st.image(buf.getvalue(), caption="Scan with Google Authenticator")
            st.code(secret, language="text")

    # Parent Link
    if not st.session_state.is_parent and not st.session_state.is_admin:
        st.subheader("Link to Parent")
        parent_email = st.text_input("Parent's Email")
        parent_pass = st.text_input("Parent's Password", type="password")
        if st.button("Link Parent"):
            msg = db.link_parent(st.session_state.user_id, parent_email, parent_pass)
            st.write(msg)
            if "Linked" in msg:
                st.rerun()

# ----------------------------------------------------------------------
# Parent Dashboard
# ----------------------------------------------------------------------
def parent_dashboard():
    st.header("Parent Dashboard")
    children = db.get_children(st.session_state.user_id)
    if not children:
        st.info("No children linked yet.")
        return

    for child in children:
        with st.expander(f"**{child['name'] or child['email']}**"):
            activity = db.get_user_activity(child["user_id"], 7)
            if activity:
                df = pd.DataFrame(activity)
                df["date"] = pd.to_datetime(df["timestamp"]).dt.date
                daily = df.groupby("date")["duration_minutes"].sum()
                st.bar_chart(daily)
                st.write("**Last 7 Days Total:**", int(daily.sum()), "minutes")
            else:
                st.write("No activity yet.")

            st.write("**Quiz Rankings**")
            for subject in ["Mathematics", "English", "Kiswahili", "Biology"]:
                rankings = db.get_subject_rankings(subject)
                if not rankings.empty and child["name"] in rankings["user"].values:
                    rank = rankings[rankings["user"] == child["name"]].index[0] + 1
                    score = rankings[rankings["user"] == child["name"]]["avg_score"].values[0]
                    st.write(f"**{subject}**: #{rank} – {score:.1f}%")

# ----------------------------------------------------------------------
# Main App
# ----------------------------------------------------------------------
def main():
    init_session_state()

    if not st.session_state.logged_in:
        st.title("LearnFlow AI – Login")
        col1, col2 = st.columns(2)
        with col1:
            email = st.text_input("Email")
        with col2:
            password = st.text_input("Password", type="password")
        totp = st.text_input("2FA Code (if enabled)")

        if st.button("Login", type="primary"):
            success, msg, state = login_user(email.lower(), password, totp)
            st.write(msg)
            if success:
                st.rerun()
        return

    # Premium check
    if not db.check_premium(st.session_state.user_id):
        with st.sidebar:
            st.warning("Upgrade to Premium for unlimited access!")
            if st.button("Pay KSh 500 via M-Pesa"):
                phone = st.text_input("Your Phone (e.g. 0712345678)")
                code = st.text_input("M-Pesa Code")
                if st.button("Submit Payment"):
                    db.add_manual_payment(st.session_state.user_id, phone, code)
                    st.success("Payment submitted! Admin will activate in <5 mins.")

    # Tabs
    tabs = st.tabs(["Chat", "PDF Upload", "Progress", "Exam Practice", "Essay", "Premium", "Settings"])
    if st.session_state.is_parent:
        parent_tab = st.tabs(["Parent Dashboard"])[0]
        with parent_tab:
            parent_dashboard()

    with tabs[0]:  # Chat
        st.header("AI Tutor Chat")
        subject = st.selectbox("Choose Subject", options=list(SUBJECT_PROMPTS.keys()))
        if "messages" not in st.session_state:
            st.session_state.messages = []

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

        if prompt := st.chat_input("Ask anything..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.write(prompt)

            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    enhanced = get_enhanced_prompt(subject, prompt)
                    response = ai_engine.generate(enhanced)
                st.write(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

    with tabs[6]:  # Settings
        settings_tab()

if __name__ == "__main__":
    main()
