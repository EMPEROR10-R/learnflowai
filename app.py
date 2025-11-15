# app.py
import streamlit as st
import logging
import bcrypt
import json
from datetime import date

# ────────────────────────────── DEBUG MODE (TEMP) ──────────────────────────────
st.set_page_config(page_title="LearnFlow AI", page_icon="Flag of Kenya", layout="wide")
st.markdown("**APP LOADED – DEBUG ON**", unsafe_allow_html=True)

# ────────────────────────────── LOGGING ──────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ────────────────────────────── SAFE IMPORTS ──────────────────────────────
try:
    from database import Database
    from ai_engine import AIEngine
    from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES
except Exception as e:
    st.error(f"Import failed: {e}")
    st.stop()

# ────────────────────────────── CSS (FIXED: unsafe_allow_html=True) ──────────────────────────────
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
    .tab-header {font-weight:bold; color:#009E60;}
    .premium-header {font-size:1.6rem; font-weight:bold; color:#FFD700; text-align:center;}
</style>
""", unsafe_allow_html=True)  # ← FIXED: was "tas=True"

# ────────────────────────────── INITIALIZERS ──────────────────────────────
@st.cache_resource
def init_db():
    try:
        db = Database()
        db.conn.execute("PRAGMA journal_mode=WAL;")
        return db
    except Exception as e:
        st.error(f"DB error: {e}")
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
            st.warning("No GEMINI_API_KEY – AI disabled")
            return AIEngine("")
        return AIEngine(key)
    except Exception as e:
        st.error(f"AI init error: {e}")
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
    try:
        css = f"body{{filter:brightness({st.session_state.brightness}%);font-family:{st.session_state.font};}}"
        if st.session_state.theme == "dark":
            css += "body{background:#222;color:#eee;}"
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)
    except:
        pass

# ────────────────────────────── WELCOME SCREEN (UNCHANGED) ──────────────────────────────
def welcome_screen():
    st.markdown('<div class="welcome-box"><h1>LearnFlow AI</h1><p>Your Kenyan AI Tutor</p><p>KCPE • KPSEA • KJSEA • KCSE</p></div>', unsafe_allow_html=True)
    _, c, _ = st.columns([1,1,1])
    with c:
        if st.button("Start Learning!", type="primary", use_container_width=True):
            st.session_state.show_welcome = False
            st.rerun()

# ────────────────────────────── LOGIN BLOCK (UNCHANGED) ──────────────────────────────
def login_block():
    if st.session_state.logged_in:
        return

    with st.container():
        st.markdown("### Login / Sign Up")
        choice = st.radio("Action", ["Login", "Sign Up"], horizontal=True, label_visibility="collapsed")
        email = st.text_input("Email", key=f"{choice.lower()}_email")
        pwd = st.text_input("Password", type="password", key=f"{choice.lower()}_pwd")
        totp = st.text_input("2FA Code (if enabled)", key="totp") if choice == "Login" else ""

        if st.button(choice, type="primary"):
            try:
                if len(pwd) < 6:
                    st.error("Password ≥6 chars")
                elif choice == "Sign Up":
                    uid = db.create_user(email, pwd)
                    st.success("Created! Log in.") if uid else st.error("Email taken")
                else:
                    user = db.get_user_by_email(email)
                    if not user or not bcrypt.checkpw(pwd.encode(), user["password_hash"].encode()):
                        st.error("Wrong credentials")
                    elif hasattr(db, 'is_2fa_enabled') and db.is_2fa_enabled(user["user_id"]) and not db.verify_2fa_code(user["user_id"], totp):
                        st.error("Bad 2FA")
                    else:
                        db.update_user_activity(user["user_id"])
                        st.session_state.update({
                            "logged_in": True, "user_id": user["user_id"],
                            "is_admin": user["role"] == "admin", "user": user,
                            "is_parent": bool(user.get("parent_id"))
                        })
                        st.success("Logged in!")
                        st.rerun()
            except Exception as e:
                st.error(f"Login error: {e}")

        st.info("**Demo:** `kingmumo15@gmail.com` / `@Yoounruly10`")

# ────────────────────────────── SIDEBAR (UNCHANGED) ──────────────────────────────
def sidebar():
    try:
        with st.sidebar:
            st.markdown("## LearnFlow AI")
            user = db.get_user(st.session_state.user_id) or {}
            if user.get("profile_pic"):
                st.image(user["profile_pic"], width=100)
            if db.check_premium(st.session_state.user_id):
                st.markdown('<span class="premium-badge">PREMIUM</span>', unsafe_allow_html=True)

            streak = getattr(db, 'update_streak', lambda x: 0)(st.session_state.user_id)
            st.markdown(f'<span class="streak-badge">Streak: {streak} days</span>', unsafe_allow_html=True)

            st.session_state.current_subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))

            st.markdown("### Badges")
            badges = json.loads(user.get("badges", "[]"))
            for b in badges[:5]:
                st.markdown(f"**Trophy** {BADGES.get(b, b)}", unsafe_allow_html=True)
    except Exception as e:
        st.sidebar.error(f"Sidebar error: {e}")

# ────────────────────────────── TABS (ALL FEATURES PRESERVED) ──────────────────────────────
def chat_tab():
    try:
        st.markdown("### Chat Tutor")
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []

        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        if prompt := st.chat_input("Ask..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    resp = ai_engine.generate_response(prompt, get_enhanced_prompt(st.session_state.current_subject, prompt))
                    st.markdown(resp)
                    st.session_state.chat_history.append({"role": "assistant", "content": resp})
            if hasattr(db, 'add_chat_history'):
                db.add_chat_history(st.session_state.user_id, st.session_state.current_subject, prompt, resp)
            if hasattr(db, 'add_score'):
                db.add_score(st.session_state.user_id, "chat", 10)
    except Exception as e:
        st.error(f"Chat error: {e}")

def pdf_tab():
    try:
        st.markdown("### PDF Upload")
        uploaded = st.file_uploader("Upload PDF", type="pdf")
        if uploaded:
            with st.spinner("Reading..."):
                text = ai_engine.extract_text_from_pdf(uploaded.read())
            st.text_area("Text:", text, height=300)
    except Exception as e:
        st.error(f"PDF error: {e}")

def progress_tab():
    st.markdown("### Progress")
    st.write("Coming soon.")

def exam_tab():
    try:
        st.markdown("### Exam Prep")
        if "exam_questions" not in st.session_state:
            subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))
            num = st.number_input("Questions", 1, 10, 5)
            if st.button("Generate"):
                with st.spinner("Creating..."):
                    st.session_state.exam_questions = ai_engine.generate_exam_questions(subject, "KCSE", num)
                    st.session_state.user_answers = {}
                st.rerun()
        else:
            qs = st.session_state.exam_questions
            for i, q in enumerate(qs):
                st.markdown(f"**Q{i+1}:** {q['question']}")
                st.session_state.user_answers[i] = st.radio("Choose", q['options'], key=f"ans{i}")
            if st.button("Submit"):
                res = ai_engine.grade_mcq(qs, st.session_state.user_answers)
                st.markdown(f"**Score: {res['percentage']}%**")
                for r in res["results"]:
                    icon = "Correct" if r["is_correct"] else "Wrong"
                    st.markdown(f"- {icon} **{r['question']}**")
                del st.session_state.exam_questions, st.session_state.user_answers
    except Exception as e:
        st.error(f"Exam error: {e}")

def essay_tab():
    try:
        st.markdown("### Essay Grader")
        essay = st.text_area("Essay", height=200)
        if st.button("Grade") and essay:
            with st.spinner("Grading..."):
                res = ai_engine.grade_essay(essay, "Kenyan curriculum")
                st.markdown(f"**Score: {res['score']}/100** – {res['feedback']}")
    except Exception as e:
        st.error(f"Essay error: {e}")

def premium_tab():
    st.markdown("### Premium")
    st.info("Send KES 500 to `0701617120`")
    phone = st.text_input("Phone")
    code = st.text_input("M-Pesa Code")
    if st.button("Submit"):
        if phone and code:
            db.add_manual_payment(st.session_state.user_id, phone, code)
            st.success("Submitted!")
        else:
            st.error("Fill both")

def settings_tab():
    st.markdown("### Settings")
    st.write("Coming soon.")

def parent_dashboard():
    st.markdown("### Parent Dashboard")
    st.write("Track child – coming soon.")

def admin_dashboard():
    if not st.session_state.is_admin:
        st.error("Access denied")
        return
    st.markdown("## Admin")
    st.write("Manage users – coming soon.")

# ────────────────────────────── MAIN (SAFE) ──────────────────────────────
def main():
    try:
        init_session()
        apply_theme()

        if st.session_state.show_welcome:
            welcome_screen()
            return

        login_block()

        if not st.session_state.logged_in:
            st.info("Log in to continue.")
            return

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
        if st.session_state.is_parent:
            with tab_objs[tabs.index("Parent Dashboard")]: parent_dashboard()
        if st.session_state.is_admin:
            with tab_objs[tabs.index("Admin Dashboard")]: admin_dashboard()

    except Exception as e:
        st.error(f"**CRASH**: {e}")
        logger.error(f"App crash: {e}", exc_info=True)

if __name__ == "__main__":
    main()
