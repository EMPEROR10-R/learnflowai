# app.py
import streamlit as st
import logging
import bcrypt
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES
import pandas as pd
from datetime import date
import json

# ────────────────────────────── LOGGING ──────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ────────────────────────────── CONFIG ──────────────────────────────
st.set_page_config(page_title="LearnFlow AI", page_icon="🇰🇪", layout="wide")

# Debug: Prove app loads
st.markdown("✅ **APP LOADED SUCCESSFULLY!** (No white screen)", unsafe_allow_html=True)

# ────────────────────────────── CSS ──────────────────────────────
st.markdown("""
<style>
    .main-header {font-size:2.8rem; font-weight:bold;
        background:linear-gradient(135deg,#009E60,#FFD700,#CE1126);
        -webkit-background-clip:text; -webkit-text-fill-color:transparent;
        text-align:center;}
    .welcome-box {background:linear-gradient(135deg,#009E60,#FFD700);
        padding:50px; border-radius:20px; color:white; text-align:center;}
    .streak-badge {background:linear-gradient(135deg,#FF6B6B,#FFE66D);
        padding:6px 14px; border-radius:20px; color:white; font-weight:bold;}
    .premium-badge {background:#FFD700; color:#000; padding:4px 10px; border-radius:12px; font-weight:bold;}
    .leaderboard {background:#f0f8ff; padding:20px; border-radius:10px; box-shadow:0 4px 8px rgba(0,0,0,0.1);}
    .badge-item {font-size:1.2em; color:#FFD700;}
    .tab-header {font-weight:bold; color:#009E60;}
    .premium-header {font-size:1.6rem; font-weight:bold; color:#FFD700; text-align:center;}
</style>
""", unsafe_allow_html=True)

# ────────────────────────────── INITIALIZERS ──────────────────────────────
@st.cache_resource
def init_db():
    try:
        db = Database()
        db.conn.execute("PRAGMA journal_mode=WAL;")
        return db
    except Exception as e:
        st.error(f"Database error: {str(e)} – Using dummy mode.")
        logger.error(f"DB init failed: {e}")
        class Dummy:
            def __getattr__(self, _): return lambda *a, **k: None
            def get_leaderboard(self, _): return []
            def check_premium(self, _): return False
            def get_user(self, _): return {}
        return Dummy()

@st.cache_resource
def init_ai():
    try:
        key = st.secrets.get("GEMINI_API_KEY", "")
        if not key:
            st.warning("No GEMINI_API_KEY – AI disabled. Add in Streamlit Secrets.")
            return AIEngine("")
        return AIEngine(key)
    except Exception as e:
        st.error(f"AI init error: {str(e)}")
        return AIEngine("")

db = init_db()
ai_engine = init_ai()

# ────────────────────────────── SESSION & THEME ──────────────────────────────
def init_session():
    defaults = {
        "logged_in": False, "user_id": None, "is_admin": False, "user": None,
        "show_welcome": True, "chat_history": [], "current_subject": "Mathematics",
        "is_parent": False, "theme": "light", "brightness": 100, "font": "sans-serif"
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def apply_theme():
    css = f"body{{filter:brightness({st.session_state.brightness}%);font-family:{st.session_state.font};}}"
    if st.session_state.theme == "dark":
        css += "body{background:#222;color:#eee;}"
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

# ────────────────────────────── UI BLOCKS ──────────────────────────────
def welcome_screen():
    st.markdown('<div class="welcome-box"><h1>LearnFlow AI</h1><p>Your Kenyan AI Tutor</p><p>KCPE • KPSEA • KJSEA • KCSE</p></div>', unsafe_allow_html=True)
    _, c, _ = st.columns([1,1,1])
    with c:
        if st.button("Start Learning!", type="primary", use_container_width=True):
            st.session_state.show_welcome = False
            st.rerun()

def login_block():
    if st.session_state.logged_in:
        return

    with st.container():
        st.markdown("### Login / Sign Up")
        col1, col2 = st.columns([1, 1])
        with col1:
            choice = st.radio("Action", ["Login", "Sign Up"], horizontal=True, label_visibility="collapsed")
        with col2:
            pass  # spacer

        email = st.text_input("Email", key=f"{choice.lower()}_email")
        pwd = st.text_input("Password", type="password", key=f"{choice.lower()}_pwd")
        totp = st.text_input("2FA Code (if enabled)", key="totp") if choice == "Login" else ""

        if st.button(choice, type="primary", use_container_width=True):
            if len(pwd) < 6:
                st.error("Password must be ≥6 characters")
            elif choice == "Sign Up":
                uid = db.create_user(email, pwd)
                if uid:
                    st.success("Account created! Please log in.")
                else:
                    st.error("Email already taken")
            else:
                user = db.get_user_by_email(email)
                if not user or not bcrypt.checkpw(pwd.encode(), user["password_hash"].encode()):
                    st.error("Invalid email or password")
                elif hasattr(db, 'is_2fa_enabled') and db.is_2fa_enabled(user["user_id"]) and not db.verify_2fa_code(user["user_id"], totp):
                    st.error("Invalid 2FA code")
                else:
                    db.update_user_activity(user["user_id"])
                    st.session_state.update({
                        "logged_in": True,
                        "user_id": user["user_id"],
                        "is_admin": user["role"] == "admin",
                        "user": user,
                        "is_parent": bool(user.get("parent_id"))
                    })
                    st.success("Logged in successfully!")
                    st.rerun()

        st.markdown("---")

def sidebar():
    with st.sidebar:
        st.markdown("## LearnFlow AI")
        user = db.get_user(st.session_state.user_id)
        if user and user.get("profile_pic"):
            st.image(user["profile_pic"], width=100)
        if db.check_premium(st.session_state.user_id):
            st.markdown('<span class="premium-badge">PREMIUM</span>', unsafe_allow_html=True)

        streak = getattr(db, 'update_streak', lambda x: 0)(st.session_state.user_id)
        st.markdown(f'<span class="streak-badge">Streak: {streak} days</span>', unsafe_allow_html=True)

        st.session_state.current_subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))

        st.markdown("### Badges")
        # FIXED: Safely parse badges – handle string or list
        badges_raw = user.get("badges") if user else "[]"
        if isinstance(badges_raw, str):
            badges = json.loads(badges_raw)
        else:
            badges = badges_raw or []
        for b in badges[:5]:
            st.markdown(f"<span class='badge-item'>🏅 {BADGES.get(b, b)}</span>", unsafe_allow_html=True)

# ────────────────────────────── TABS ──────────────────────────────
def chat_tab():
    st.markdown('<span class="tab-header">### Chat Tutor</span>', unsafe_allow_html=True)
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask anything..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                resp = ai_engine.generate_response(prompt, get_enhanced_prompt(st.session_state.current_subject, prompt, ""))
                st.markdown(resp)
                st.session_state.chat_history.append({"role": "assistant", "content": resp})

        if hasattr(db, 'add_chat_history'):
            db.add_chat_history(st.session_state.user_id, st.session_state.current_subject, prompt, resp)
        if hasattr(db, 'add_score'):
            db.add_score(st.session_state.user_id, "chat", 10)

def pdf_tab():
    st.markdown('<span class="tab-header">### PDF Upload</span>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")
    if uploaded_file is not None:
        with st.spinner("Extracting text..."):
            text = ai_engine.extract_text_from_pdf(uploaded_file.read())
        st.text_area("Extracted Text:", text, height=300)
    else:
        st.info("Upload a PDF to extract text (PyPDF2)")

def progress_tab():
    st.markdown('<span class="tab-header">### Progress</span>', unsafe_allow_html=True)
    st.write("Progress tracking coming soon.")

def exam_tab():
    st.markdown('<span class="tab-header">### Exam Prep</span>', unsafe_allow_html=True)
    if "exam_questions" not in st.session_state:
        subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()), key="exam_subject")
        exam_type = st.selectbox("Exam Type", list(EXAM_TYPES.keys()), key="exam_type")
        num_questions = st.number_input("Questions", 1, 20, 5, key="num_q")
        if st.button("Generate Exam"):
            with st.spinner("Generating..."):
                st.session_state.exam_questions = ai_engine.generate_exam_questions(subject, exam_type, num_questions)
                st.session_state.user_answers = {}
            st.rerun()
    else:
        qs = st.session_state.exam_questions
        for i, q in enumerate(qs):
            st.markdown(f"**Q{i+1}:** {q['question']}")
            st.session_state.user_answers[i] = st.radio("Choose", q['options'], key=f"ans{i}")
        if st.button("Submit Exam"):
            with st.spinner("Grading..."):
                res = ai_engine.grade_mcq(qs, st.session_state.user_answers)
                if hasattr(db, 'add_score'):
                    db.add_score(st.session_state.user_id, "exam", res["percentage"])
                if res["percentage"] == 100:
                    if hasattr(db, 'add_badge'):
                        db.add_badge(st.session_state.user_id, "perfect_score")
                    st.balloons()
                st.markdown(f"**Score: {res['percentage']}%**")
                for r in res["results"]:
                    icon = "✅ Correct" if r["is_correct"] else "❌ Wrong"
                    st.markdown(f"- {icon} **{r['question']}**  \n  Your: `{r['user_answer']}`  \n  Correct: `{r['correct_answer']}`  \n  {r['feedback']}")
            del st.session_state.exam_questions, st.session_state.user_answers

def essay_tab():
    st.markdown('<span class="tab-header">### Essay Grader</span>', unsafe_allow_html=True)
    essay = st.text_area("Paste your essay", height=200)
    rubric = st.text_area("Rubric (optional)", value="Structure, grammar, content relevance to Kenyan curriculum.")
    if st.button("Grade Essay") and essay.strip():
        with st.spinner("Grading..."):
            res = ai_engine.grade_essay(essay, rubric)
            if hasattr(db, 'add_score'):
                db.add_score(st.session_state.user_id, "essay", res["score"])
            if res["score"] >= 90:
                if hasattr(db, 'add_badge'):
                    db.add_badge(st.session_state.user_id, "quiz_ace")
                st.balloons()
            st.markdown(f"**Score: {res['score']}/100** – {res['feedback']}")

def premium_tab():
    st.markdown('<div class="premium-header"><strong>Upgrade to Premium – KES 500/month</strong></div>', unsafe_allow_html=True)
    st.info("**Send KES 500 to M-Pesa:** `0701617120`")
    phone = st.text_input("Your M-Pesa Phone Number")
    code = st.text_input("M-Pesa Transaction Code")
    if st.button("Submit Proof", type="primary"):
        if phone and code:
            if hasattr(db, 'add_manual_payment'):
                db.add_manual_payment(st.session_state.user_id, phone, code)
            st.success("Submitted! Admin will activate in 24 hrs.")
            st.balloons()
        else:
            st.error("Fill both fields")

def settings_tab():
    st.markdown('<span class="tab-header">### Settings</span>', unsafe_allow_html=True)
    st.write("Theme, 2FA, and more – coming soon.")

def parent_dashboard():
    st.markdown('<span class="tab-header">### Parent Dashboard</span>', unsafe_allow_html=True)
    st.write("Track your child's progress – coming soon.")

def admin_dashboard():
    if not st.session_state.is_admin:
        st.error("Access denied")
        return
    st.markdown('<span class="tab-header">## Admin Dashboard</span>', unsafe_allow_html=True)
    st.write("User management, payments, analytics – coming soon.")

# ────────────────────────────── MAIN ──────────────────────────────
def main():
    init_session()
    apply_theme()

    if st.session_state.show_welcome:
        welcome_screen()
        return

    # Always show login if not logged in
    login_block()

    # If still not logged in → show message and stop
    if not st.session_state.logged_in:
        st.info("Please log in to access LearnFlow AI.")
        return

    # USER IS LOGGED IN → FULL APP
    sidebar()

    tabs = ["Chat Tutor", "PDF Upload", "Progress", "Exam Prep", "Essay Grader", "Settings"]
    if not db.check_premium(st.session_state.user_id):
        tabs.insert(5, "Premium")
    if st.session_state.is_parent:
        tabs.append("Parent Dashboard")
    if st.session_state.is_admin:
        tabs.append("Admin Dashboard")

    tab_objs = st.tabs(tabs)
    idx = 0
    with tab_objs[idx]: chat_tab(); idx += 1
    with tab_objs[idx]: pdf_tab(); idx += 1
    with tab_objs[idx]: progress_tab(); idx += 1
    with tab_objs[idx]: exam_tab(); idx += 1
    with tab_objs[idx]: essay_tab(); idx += 1
    if "Premium" in tabs:
        with tab_objs[tabs.index("Premium")]: premium_tab()
    with tab_objs[tabs.index("Settings")]: settings_tab()
    if st.session_state.is_parent and "Parent Dashboard" in tabs:
        with tab_objs[tabs.index("Parent Dashboard")]: parent_dashboard()
    if st.session_state.is_admin and "Admin Dashboard" in tabs:
        with tab_objs[tabs.index("Admin Dashboard")]: admin_dashboard()

if __name__ == "__main__":
    main()
