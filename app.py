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
        st.error(f"Database error: {str(e)}")
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
        key = st.secrets["GEMINI_API_KEY"]
        return AIEngine(key)
    except KeyError:
        st.error("GEMINI_API_KEY not set in secrets – add it in Cloud Settings > Secrets.")
        return AIEngine("")
    except Exception as e:
        st.error(f"AI init error: {str(e)}")
        logger.warning(f"AI init failed: {e}")
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
        if k not in st.session_state: st.session_state[k] = v

def apply_theme():
    css = f"body{{filter:brightness({st.session_state.brightness}%);font-family:{st.session_state.font};}}"
    if st.session_state.theme == "dark": css += "body{background:#222;color:#eee;}"
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
    if st.session_state.logged_in: return
    st.markdown("### Login / Sign Up")
    choice = st.radio("Action", ["Login", "Sign Up"], horizontal=True)
    email = st.text_input("Email", key=f"{choice.lower()}_email")
    pwd = st.text_input("Password", type="password", key=f"{choice.lower()}_pwd")
    totp = st.text_input("2FA (if enabled)", key="totp") if choice=="Login" else ""

    if st.button(choice):
        if len(pwd) < 6: st.error("Password ≥6 chars")
        elif choice == "Sign Up":
            uid = db.create_user(email, pwd)
            st.success("Created! Log in.") if uid else st.error("Email taken")
        else:
            user = db.get_user_by_email(email)
            if not user or not bcrypt.checkpw(pwd.encode(), user["password_hash"].encode()):
                st.error("Wrong credentials")
            elif db.is_2fa_enabled(user["user_id"]) and not db.verify_2fa_code(user["user_id"], totp):
                st.error("Bad 2FA code")
            else:
                db.update_user_activity(user["user_id"])
                st.session_state.update({
                    "logged_in": True, "user_id": user["user_id"],
                    "is_admin": user["role"]=="admin", "user": user,
                    "is_parent": bool(user.get("parent_id"))
                })
                st.rerun()
    st.stop()

def sidebar():
    with st.sidebar:
        st.markdown("## LearnFlow AI")
        user = db.get_user(st.session_state.user_id)
        if user and user.get("profile_pic"):
            st.image(user["profile_pic"], width=100)
        if db.check_premium(st.session_state.user_id):
            st.markdown('<span class="premium-badge">PREMIUM</span>', unsafe_allow_html=True)
        streak = db.update_streak(st.session_state.user_id)
        st.markdown(f'<span class="streak-badge">Streak: {streak} days</span>', unsafe_allow_html=True)
        st.session_state.current_subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))
        if st.button("Logout"):
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()

# ────────────────────────────── TABS ──────────────────────────────
def chat_tab():
    st.markdown(f'<span class="tab-header">### {st.session_state.current_subject} Tutor</span>', unsafe_allow_html=True)
    for m in st.session_state.chat_history:
        role = "You" if m["role"]=="user" else "AI"
        st.markdown(f"**{role}:** {m['content']}")
    q = st.text_area("Ask:", height=100)
    if st.button("Send") and q:
        st.session_state.chat_history.append({"role":"user","content":q})
        with st.spinner("Thinking…"):
            resp = ai_engine.generate_response(q, get_enhanced_prompt(st.session_state.current_subject, q, ""))
        st.session_state.chat_history.append({"role":"assistant","content":resp})
        db.add_chat_history(st.session_state.user_id, st.session_state.current_subject, q, resp)
        db.add_score(st.session_state.user_id, "chat", 10)

def pdf_tab():
    st.write("PDF Upload tab – coming soon.")

def progress_tab():
    st.write("Progress tracking – coming soon.")

def exam_tab():
    st.markdown('<span class="tab-header">### Exam Prep</span>', unsafe_allow_html=True)
    if "exam_questions" not in st.session_state:
        subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))
        exam_type = st.selectbox("Exam Type", list(EXAM_TYPES.keys()))
        num_questions = st.number_input("Number of Questions", min_value=1, max_value=20, value=5)
        if st.button("Generate Exam"):
            with st.spinner("Generating questions…"):
                st.session_state.exam_questions = ai_engine.generate_exam_questions(subject, exam_type, num_questions)
                st.session_state.user_answers = {}
            st.rerun()
    else:
        qs = st.session_state.exam_questions
        for i, q in enumerate(qs):
            st.markdown(f"**Q{i+1}:** {q['question']}")
            st.session_state.user_answers[i] = st.radio("Choose", q['options'], key=f"ans{i}")
        if st.button("Submit"):
            with st.spinner("Grading…"):
                res = ai_engine.grade_mcq(qs, st.session_state.user_answers)
                db.add_score(st.session_state.user_id, "exam", res["percentage"])
                if res["percentage"] == 100:
                    db.add_badge(st.session_state.user_id, "perfect_score")
                    st.balloons()
                st.markdown(f"**Score: {res['percentage']}%**")
                for r in res["results"]:
                    icon = "Correct" if r["is_correct"] else "Wrong"
                    st.markdown(f"- {icon} **{r['question']}**  \n  Your: `{r['user_answer']}`  \n  Correct: `{r['correct_answer']}`  \n  {r['feedback']}")
            del st.session_state.exam_questions, st.session_state.user_answers

def essay_tab():
    st.markdown('<span class="tab-header">### Essay Grader</span>', unsafe_allow_html=True)
    essay = st.text_area("Paste essay", height=200)
    rubric = st.text_area("Rubric (optional)", value="Structure, grammar, content relevance to Kenyan curriculum.")
    if st.button("Grade") and essay:
        with st.spinner("Grading…"):
            res = ai_engine.grade_essay(essay, rubric)
            db.add_score(st.session_state.user_id, "essay", res["score"])
            if res["score"] >= 90:
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
            db.add_manual_payment(st.session_state.user_id, phone, code)
            st.success("Submitted! Admin will activate in 24 hrs.")
            st.balloons()
        else:
            st.error("Fill both fields")

def settings_tab():
    st.markdown('<span class="tab-header">### Settings</span>', unsafe_allow_html=True)
    # 2FA, theme, etc. (as in original)
    st.write("Settings panel – full version in original code.")

def parent_dashboard():
    st.markdown('<span class="tab-header">### Parent Dashboard</span>', unsafe_allow_html=True)
    st.write("Child tracking – coming soon.")

def admin_dashboard():
    if not st.session_state.is_admin: st.error("Access denied"); return
    st.markdown('<span class="tab-header">## Admin Dashboard</span>', unsafe_allow_html=True)
    st.write("User management – full version in original.")

# ────────────────────────────── MAIN ──────────────────────────────
def main():
    st.write("App is running! If you see this, code loaded.")
    init_session()
    apply_theme()
    if st.session_state.show_welcome: welcome_screen(); return
    login_block()
    sidebar()

    tabs = ["Chat Tutor","PDF Upload","Progress","Exam Prep","Essay Grader","Settings"]
    if not db.check_premium(st.session_state.user_id):
        tabs.insert(5, "Premium")
    if st.session_state.is_parent: tabs.append("Parent Dashboard")
    if st.session_state.is_admin: tabs.append("Admin Dashboard")

    tab_objs = st.tabs(tabs)
    idx = 0
    with tab_objs[idx]: chat_tab(); idx += 1
    with tab_objs[idx]: pdf_tab(); idx += 1
    with tab_objs[idx]: progress_tab(); idx += 1
    with tab_objs[idx]: exam_tab(); idx += 1
    with tab_objs[idx]: essay_tab(); idx += 1
    if "Premium" in tabs:
        with tab_objs[tabs.index("Premium")]: premium_tab()
    with tab_objs[idx]: settings_tab(); idx += 1
    if st.session_state.is_parent and "Parent Dashboard" in tabs:
        with tab_objs[tabs.index("Parent Dashboard")]: parent_dashboard()
    if st.session_state.is_admin and "Admin Dashboard" in tabs:
        with tab_objs[tabs.index("Admin Dashboard")]: admin_dashboard()

if __name__ == "__main__":
    main()
