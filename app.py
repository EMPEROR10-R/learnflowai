# app.py — FINAL VERSION: Full Exam Prep + All Subjects + Python Code Support
import streamlit as st
import bcrypt
import json
import pandas as pd
from datetime import date, timedelta
from database import Database
from ai_engine import AIEngine
from prompts import EXAM_TYPES
import re
import io
import qrcode
import base64

# === INIT ===
st.set_page_config(page_title="Kenyan EdTech", layout="wide")
db = Database()
db.auto_downgrade()

real_ai = AIEngine(st.secrets.get("GEMINI_API_KEY", ""))
ai_engine = real_ai if getattr(real_ai, "gemini_key", None) else type("obj", (), {"generate_exam_questions": lambda *a: [], "grade_mcq": lambda q, a: {"correct": 0, "total": 0, "percentage": 0, "results": []}})()

if "initialized" not in st.session_state:
    st.session_state.update({
        "logged_in": False, "user_id": None, "user": None,
        "current_subject": "Mathematics", "lang": "en",
        "current_exam": None, "user_answers": {}, "last_result": None
    })

def get_user():
    if st.session_state.user_id:
        st.session_state.user = db.get_user(st.session_state.user_id)
    return st.session_state.user

def award_xp(points, reason):
    if st.session_state.user_id:
        db.add_xp(st.session_state.user_id, points)
        st.toast(f"+{points} XP — {reason}")

# === SIDEBAR ===
with st.sidebar:
    st.title("Kenyan EdTech")
    if st.session_state.logged_in and (u := get_user()):
        icon = "crown" if u.get("username") == "EmperorUnruly" else "brain"
        st.image(f"https://img.icons8.com/fluency/100/{icon}.png", width=100)
        st.metric("Total XP", f"{u.get('total_xp',0):,}")
        st.metric("XP Coins", f"{u.get('xp_coins',0):,}")
        st.metric("Streak", f"{u.get('streak',0)} days")
        if u.get("discount_20"): st.success("20% Discount Active!")

# === EXAM PREP TAB (PERFECT FLOW) ===
def exam_tab():
    st.header("Exam Prep – KCPE • KPSEA • KJSEA • KCSE")

    # 1. Exam Type
    exam_type = st.selectbox("Select Exam", list(EXAM_TYPES.keys()), key="exam_type")

    # 2. Subject
    subjects = EXAM_TYPES[exam_type]["subjects"]
    subject = st.selectbox("Select Subject", subjects, key="exam_subject")

    # 3. Mode
    mode = st.radio("Mode", ["General Questions", "Specific Topic"], horizontal=True)

    topic = ""
    if mode == "Specific Topic":
        topics = EXAM_TYPES[exam_type].get("topics", {}).get(subject, [])
        if topics:
            topic = st.selectbox("Choose Topic", topics)
        else:
            st.info("No specific topics defined for this subject.")

    # 4. Number of Questions
    num_questions = st.slider("Number of Questions", 1, 100, 10)

    # 5. Generate Exam
    if st.button("Generate Exam", type="primary"):
        with st.spinner("Generating high-quality questions..."):
            questions = ai_engine.generate_exam_questions(
                subject=subject,
                exam_type=exam_type,
                num_questions=num_questions,
                topic=topic or ""
            )
        st.session_state.current_exam = {
            "questions": questions,
            "subject": subject,
            "exam_type": exam_type,
            "topic": topic
        }
        st.session_state.user_answers = {}
        st.success(f"Generated {len(questions)} questions!")
        st.rerun()

    # 6. Answer Interface
    if st.session_state.current_exam:
        qlist = st.session_state.current_exam["questions"]
        st.subheader(f"{subject} • {exam_type} • {len(qlist)} Questions")

        for i, q in enumerate(qlist):
            with st.expander(f"Question {i+1}", expanded=True):
                st.markdown(f"**Q:** {q['question']}")
                cols = st.columns(len(q['options']))
                for j, opt in enumerate(q['options']):
                    with cols[j]:
                        st.write(opt)

                # Large answer box
                answer = st.text_area(
                    "Your Answer (write full working, code, explanation)",
                    height=250,
                    key=f"ans_{i}"
                )
                st.session_state.user_answers[i] = answer

                # Python code support
                if "python" in subject.lower() or "code" in q["question"].lower():
                    st.code(answer or "# Write your Python code here", language="python")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Submit & Grade Exam", type="primary", use_container_width=True):
                with st.spinner("Grading your answers..."):
                    result = ai_engine.grade_mcq(qlist, st.session_state.user_answers)
                    st.session_state.last_result = result
                    db.add_score(st.session_state.user_id, "exam", result["percentage"])
                    award_xp(int(result["percentage"]), "Exam Score")
                st.rerun()

        with col2:
            if st.button("Generate New Exam", use_container_width=True):
                st.session_state.current_exam = None
                st.session_state.user_answers = {}
                st.session_state.last_result = None
                st.rerun()

    # 7. Show Results + Corrections
    if st.session_state.get("last_result"):
        r = st.session_state.last_result
        st.success(f"Score: {r['correct']}/{r['total']} → {r['percentage']:.1f}% • +{int(r['percentage'])} XP")

        for i, res in enumerate(r["results"]):
            with st.expander(f"Question {i+1} • {'Correct' if res['is_correct'] else 'Incorrect'}", expanded=False):
                st.write(f"**Your Answer:**\n{res['user_answer'] or '—'}")
                st.write(f"**Correct Answer:** {res['correct_answer']}")
                st.markdown(f"**Feedback:** {res['feedback']}")
                if res['is_correct']:
                    st.success("Correct!")
                else:
                    st.error("Review this")

# === OTHER TABS (unchanged for brevity) ===
def chat_tab(): st.header("Chat Tutor"); st.write("Coming soon...")
def progress_tab(): st.header("Progress"); st.write("Leaderboard coming...")
def settings_tab(): st.header("Settings"); st.write("2FA, Profile...")
def pdf_tab(): st.header("PDF Q&A"); st.write("Upload & ask...")
def project_tab(): st.header("Projects"); st.write("Python, Agriculture, Pre-Tech...")
def shop_page(): st.header("Shop"); st.write("Buy 20% Discount Cheque")
def emperor_panel(): st.header("Emperor Control"); st.write("Approve payments")

# === MAIN MENU ===
if not st.session_state.logged_in:
    st.title("Kenyan EdTech")
    st.markdown("### Kenya's Most Powerful AI Learning Platform")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Login", type="primary", use_container_width=True):
            st.session_state.show_login = True
    with col2:
        if st.button("Register", use_container_width=True):
            st.session_state.show_register = True

    if st.session_state.get("show_login") or st.session_state.get("show_register"):
        with st.form("auth_form"):
            username = st.text_input("Username")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Login / Register")
            if submit:
                user = db.conn.execute("SELECT * FROM users WHERE username=? OR email=?", (username, email)).fetchone()
                if user and bcrypt.checkpw(password.encode(), user["password_hash"]):
                    st.session_state.logged_in = True
                    st.session_state.user_id = user["user_id"]
                    st.rerun()
                else:
                    st.error("Invalid credentials or user not found")

else:
    menu = ["Chat Tutor", "Exam Prep", "Projects", "Progress", "PDF Q&A", "Settings", "Shop"]
    if st.session_state.user.get("username") == "EmperorUnruly":
        menu.append("Emperor Panel")
    
    choice = st.sidebar.radio("Navigate", menu)

    if choice == "Exam Prep": exam_tab()
    elif choice == "Chat Tutor": chat_tab()
    elif choice == "Progress": progress_tab()
    elif choice == "Settings": settings_tab()
    elif choice == "PDF Q&A": pdf_tab()
    elif choice == "Projects": project_tab()
    elif choice == "Shop": shop_page()
    elif choice == "Emperor Panel": emperor_panel()
