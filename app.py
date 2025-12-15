# app.py — FINAL LOGIN FLOW FIX | STREAMLIT CLOUD SAFE

import streamlit as st
import bcrypt
import pandas as pd
from datetime import datetime

from database import Database
from ai_engine import AIEngine

# ---------------- CONFIG ----------------
st.set_page_config(
    page_title="Kenyan EdTech",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------- INIT ----------------
db = Database()
db.auto_downgrade()
ai_engine = AIEngine()

# ---------------- SESSION STATE ----------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.page = "landing"

# ---------------- HERO ----------------
st.markdown("""
<h1 style="text-align:center;color:gold;">KENYAN EDTECH</h1>
<p style="text-align:center;">AI Exam Prep & Projects</p>
""", unsafe_allow_html=True)

# ---------------- AUTH FLOW ----------------
if not st.session_state.logged_in:

    # -------- LANDING --------
    if st.session_state.page == "landing":
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("LOGIN", type="primary", use_container_width=True):
                st.session_state.page = "login"
                st.rerun()
            if st.button("REGISTER FREE", use_container_width=True):
                st.session_state.page = "register"
                st.rerun()

    # -------- LOGIN --------
    elif st.session_state.page == "login":
        st.subheader("🔐 Login")

        email = st.text_input("Email")
        password = st.text_input("Password", type="password")

        if st.button("Login", type="primary"):
            user = db.get_user_by_email(email)
            if user and bcrypt.checkpw(password.encode(), user["password_hash"]):
                st.session_state.logged_in = True
                st.session_state.user_id = user["user_id"]
                st.session_state.page = "app"
                st.rerun()
            else:
                st.error("Invalid credentials")

        if st.button("⬅ Back"):
            st.session_state.page = "landing"
            st.rerun()

    # -------- REGISTER --------
    elif st.session_state.page == "register":
        st.subheader("📝 Register")

        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm Password", type="password")

        if st.button("Create Account", type="primary"):
            if password != confirm:
                st.error("Passwords do not match")
            else:
                uid = db.create_user(email, password)
                if uid:
                    st.session_state.logged_in = True
                    st.session_state.user_id = uid
                    st.session_state.page = "app"
                    st.rerun()
                else:
                    st.error("Email already exists")

        if st.button("⬅ Back"):
            st.session_state.page = "landing"
            st.rerun()

# ---------------- MAIN APP ----------------
else:
    user = db.get_user(st.session_state.user_id)

    with st.sidebar:
        st.success(f"Welcome {user.get('username') or user['email']}")
        if st.button("Logout"):
            st.session_state.clear()
            st.rerun()

    tab1, tab2, tab3 = st.tabs(["AI Tutor", "Projects", "Leaderboards"])

    with tab1:
        st.subheader("🤖 AI Tutor")
        prompt = st.text_area("Ask anything")
        if st.button("Ask AI"):
            st.write(ai_engine.generate_response(prompt))

    with tab2:
        st.subheader("📂 Projects")
        title = st.text_input("Project title")
        desc = st.text_area("Description")
        if st.button("Submit"):
            if title and desc:
                db.submit_project(st.session_state.user_id, "General", title, desc)
                st.success("Submitted")

    with tab3:
        st.subheader("🏆 Leaderboard")
        data = db.get_leaderboard()
        st.dataframe(pd.DataFrame(data))
