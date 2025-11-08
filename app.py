# app.py
import streamlit as st
import os
from datetime import datetime, timedelta
import pandas as pd
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS
import threading
import logging
import jwt
import bcrypt
import pyotp
import qrcode
from io import BytesIO

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
    gemini_key = st.secrets.get("GEMINI_API_KEY", "")
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
    user = db.get_user_by_email(email)
    if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return False, "Invalid credentials.", None

    if db.is_2fa_enabled(user["user_id"]):
        if not totp_code:
            return False, "2FA code required.", "2fa_needed"
        if not db.verify_2fa_code(user["user_id"], totp_code):
            return False, "Invalid 2FA code.", None

    st.session_state.update({
        "user_id": user["user_id"], "user_name": user.get("name", ""), "user_email": email,
        "is_admin": user["role"] == "admin", "logged_in": True,
        "is_parent": bool(db.get_children(user["user_id"]))
    })
    db.update_user_activity(user["user_id"])
    db.log_activity(user["user_id"], "login")
    return True, "Logged in!", None

# ----------------------------------------------------------------------
# Settings Tab – 2FA + Parent Link
# ----------------------------------------------------------------------
def settings_tab():
    st.header("Settings")
    
    # 2FA
    st.subheader("Two-Factor Authentication")
    if db.is_2fa_enabled(st.session_state.user_id):
        st.success("2FA Enabled")
        if st.button("Disable 2FA"):
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET two_fa_secret = NULL WHERE user_id = ?", (st.session_state.user_id,))
            conn.commit()
            conn.close()
            st.success("2FA disabled.")
            st.rerun()
    else:
        st.info("Enable 2FA (free with Google Authenticator)")
        if st.button("Enable 2FA"):
            secret = db.generate_2fa_secret(st.session_state.user_id)
            uri = pyotp.TOTP(secret).provisioning_uri(name=st.session_state.user_email, issuer_name="LearnFlow AI")
            qr = qrcode.make(uri)
            buf = BytesIO()
            qr.save(buf, format="PNG")
            st.image(buf.getvalue(), caption="Scan with Authenticator")
            st.code(secret)

    # Parent Link
    if not st.session_state.is_parent and not st.session_state.is_admin:
        st.subheader("Link Parent")
        parent_email = st.text_input("Parent Email")
        parent_pass = st.text_input("Parent Password", type="password")
        if st.button("Link Parent"):
            msg = db.link_parent(st.session_state.user_id, parent_email, parent_pass)
            st.write(msg)

# ----------------------------------------------------------------------
# Parent Dashboard
# ----------------------------------------------------------------------
def parent_dashboard():
    st.header("Parent Dashboard")
    children = db.get_children(st.session_state.user_id)
    if not children:
        st.info("No children linked.")
        return

    for child in children:
        with st.expander(f"**{child['name'] or child['email']}**"):
            # Activity
            activity = db.get_user_activity(child["user_id"], 7)
            if activity:
                df = pd.DataFrame(activity)
                df["date"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d")
                daily = df.groupby("date").agg({"duration_minutes": "sum", "action": "count"}).rename(columns={"action": "sessions"})
                st.bar_chart(daily["duration_minutes"])
                st.write("**Last 7 Days:**", daily)
            else:
                st.write("No activity.")

            # Rankings
            st.write("**Quiz Rankings**")
            for subject in SUBJECT_PROMPTS.keys():
                rankings = db.get_subject_rankings(subject)
                if not rankings.empty and child["name"] in rankings["user"].values:
                    rank = rankings[rankings["user"] == child["name"]].index[0] + 1
                    score = rankings[rankings["user"] == child["name"]]["avg_score"].values[0]
                    st.write(f"**{subject}**: Rank #{rank} – {score}%")

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    init_session_state()

    if not st.session_state.logged_in:
        st.header("Login")
        col1, col2 = st.columns(2)
        with col1:
            email = st.text_input("Email")
        with col2:
            password = st.text_input("Password", type="password")
        totp = st.text_input("2FA Code (if enabled)")

        if st.button("Login"):
            success, msg, state = login_user(email, password, totp)
            st.write(msg)
            if success:
                st.rerun()
        return

    # Check approval
    if not db.check_premium(st.session_state.user_id):
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM manual_payments 
            WHERE user_id = ? AND status = 'approved' 
            AND processed_at > datetime('now', '-1 minute')
        """, (st.session_state.user_id,))
        if cursor.fetchone():
            st.success("Premium activated!")
            st.balloons()
            st.rerun()

    # Tabs
    tabs = st.tabs(["Chat", "PDF", "Progress", "Exam", "Essay", "Premium", "Settings"])
    if st.session_state.is_parent:
        tabs.append(st.tabs(["Parent Dashboard"])[0])
    if st.session_state.is_admin:
        tabs.append(st.tabs(["Admin"])[0])

    with tabs[6]: settings_tab()
    if st.session_state.is_parent and len(tabs) > 7:
        with tabs[7]: parent_dashboard()

if __name__ == "__main__":
    main()
