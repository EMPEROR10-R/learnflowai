# app.py
import streamlit as st
import os
import json
import uuid
import pyotp
import qrcode
from io import BytesIO
import pandas as pd
import bcrypt  # ← FIXED: Import bcrypt
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES
from utils import Translator_Utils, EssayGrader, VoiceInputHelper
import streamlit.components.v1 as components

# --------------------------------------------------------------------
# Page config
# --------------------------------------------------------------------
st.set_page_config(
    page_title="LearnFlow AI",
    page_icon="book",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --------------------------------------------------------------------
# Initialize DB & AI
# --------------------------------------------------------------------
db = Database()
ai = AIEngine()

# --------------------------------------------------------------------
# Session state
# --------------------------------------------------------------------
if "user" not in st.session_state:
    st.session_state.user = None
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "show_welcome" not in st.session_state:
    st.session_state.show_welcome = True

# --------------------------------------------------------------------
# Welcome Animation
# --------------------------------------------------------------------
def show_welcome_animation():
    if st.session_state.show_welcome:
        st.balloons()
        st.success("Welcome to **LearnFlow AI** – Your KCPE/KCSE Study Buddy!")
        st.session_state.show_welcome = False

# --------------------------------------------------------------------
# Login / Signup
# --------------------------------------------------------------------
def login_user(email: str, password: str, totp_code: str = ""):
    user = db.get_user_by_email(email)
    if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return False, "Invalid credentials.", None

    if db.is_2fa_enabled(user["user_id"]):
        if not totp_code:
            return False, "2FA code required.", "2fa_needed"
        if not db.verify_2fa_code(user["user_id"], totp_code):
            return False, "Invalid 2FA code.", None

    db.update_user_activity(user["user_id"])
    return True, "Login successful!", user

def signup_user(email: str, password: str, name: str):
    if db.get_user_by_email(email):
        return False, "Email already exists."
    user_id = db.create_user(email, password)
    if not user_id:
        return False, "Signup failed."
    return True, "Account created! Please log in."

# --------------------------------------------------------------------
# Login / Signup Block
# --------------------------------------------------------------------
def login_signup_block():
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Login")
        email = st.text_input("Email", key="login_email")
        pwd = st.text_input("Password", type="password", key="login_pwd")
        totp = st.text_input("2FA Code (if enabled)", key="login_totp")
        if st.button("Login"):
            success, msg, user = login_user(email, pwd, totp)
            st.write(msg)
            if success:
                st.session_state.user = user
                st.session_state.is_admin = user["role"] == "admin"
                st.rerun()

    with col2:
        st.subheader("Sign Up")
        name = st.text_input("Full Name", key="signup_name")
        email_s = st.text_input("Email", key="signup_email")
        pwd_s = st.text_input("Password", type="password", key="signup_pwd")
        if st.button("Create Account"):
            success, msg = signup_user(email_s, pwd_s, name)
            st.write(msg)

# --------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------
def sidebar_config():
    with st.sidebar:
        st.header(f"Hi, {st.session_state.user['name']}")
        if st.button("Logout"):
            st.session_state.user = None
            st.session_state.is_admin = False
            st.rerun()

        st.divider()
        st.caption("KCPE • KPSEA • KJSEA • KCSE")

# --------------------------------------------------------------------
# Premium Tab (Manual M-Pesa)
# --------------------------------------------------------------------
def premium_tab():
    st.subheader("Upgrade to Premium – KES 500/month")
    st.info("Pay via M-Pesa and submit proof below. Admin will activate your account.")

    phone = st.text_input("Your M-Pesa Phone (e.g. 07xx)")
    mpesa_code = st.text_input("M-Pesa Transaction Code (e.g. ABC123XYZ)")

    if st.button("Submit Proof"):
        if not phone or not mpesa_code:
            st.error("Fill all fields.")
        else:
            db.add_manual_payment(st.session_state.user["user_id"], phone, mpesa_code)
            st.success("Submitted! Admin will verify within 24 hours.")

# --------------------------------------------------------------------
# Parent Dashboard
# --------------------------------------------------------------------
def parent_dashboard():
    if st.session_state.user.get("parent_id"):
        st.error("You are a child. Access denied.")
        return

    children = db.get_children(st.session_state.user["user_id"])
    if not children:
        st.info("No children linked yet.")
        parent_email = st.text_input("Child's Email")
        child_pwd = st.text_input("Child's Password", type="password")
        if st.button("Link Child"):
            msg = db.link_parent(st.session_state.user["user_id"], parent_email, child_pwd)
            st.write(msg)
        return

    for child in children:
        with st.expander(f"{child['name']} ({child['email']})"):
            st.write(f"Streak: {child['streak_days']} days")
            st.write(f"Total Queries: {child['total_queries']}")
            st.write(f"Premium: {'Yes' if child['is_premium'] else 'No'}")

            activity = db.get_user_activity(child["user_id"], days=7)
            if activity:
                df = pd.DataFrame(activity)
                st.dataframe(df[["action", "timestamp"]])

# --------------------------------------------------------------------
# Admin Dashboard
# --------------------------------------------------------------------
def admin_dashboard():
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
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Approve", key=f"approve_{p['id']}"):
                        if db.approve_manual_payment(p["id"]):
                            st.success("Approved!")
                            st.rerun()
                with col2:
                    if st.button("Reject", key=f"reject_{p['id']}"):
                        db.reject_manual_payment(p["id"])
                        st.error("Rejected.")
                        st.rerun()

# --------------------------------------------------------------------
# Main App
# --------------------------------------------------------------------
def main():
    if st.session_state.show_welcome:
        show_welcome_animation()
        return

    if not st.session_state.user:
        login_signup_block()
        return

    sidebar_config()

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Chat", "PDF", "Quiz", "Premium", "Parent"])

    with tab1:
        st.subheader("AI Chat")
        subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))
        query = st.text_area("Ask anything...")
        if st.button("Send"):
            response = ai.generate_response(subject, query)
            st.write(response)
            db.add_chat_history(st.session_state.user["user_id"], subject, query, response)

    with tab2:
        st.subheader("Upload PDF")
        uploaded = st.file_uploader("Upload Notes", type="pdf")
        if uploaded:
            db.add_pdf_upload(st.session_state.user["user_id"], uploaded.name)
            st.success("Uploaded!")

    with tab3:
        st.subheader("Take Quiz")
        subject = st.selectbox("Subject", ["Math", "Science"], key="quiz_sub")
        exam = st.selectbox("Exam", EXAM_TYPES, key="quiz_exam")
        if st.button("Start Quiz"):
            # Mock quiz
            score = 8
            total = 10
            db.add_quiz_result(st.session_state.user["user_id"], subject, exam, score, total)
            st.success(f"You scored {score}/{total}!")

    with tab4:
        premium_tab()
        if st.session_state.is_admin:
            st.divider()
            admin_dashboard()

    with tab5:
        parent_dashboard()

    st.caption("LearnFlow AI – KCPE • KPSEA • KJSEA • KCSE")

# --------------------------------------------------------------------
# Run
# --------------------------------------------------------------------
if __name__ == "__main__":
    main()
