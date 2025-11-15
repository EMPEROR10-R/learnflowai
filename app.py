# app.py
import streamlit as st
import logging
import bcrypt
import json

# ────────────────────────────── PAGE CONFIG (FIXED: Use Flag of Kenya emoji) ──────────────────────────────
st.set_page_config(
    page_title="LearnFlow AI",
    page_icon="Flag of Kenya",  # ← FIXED: This works!
    layout="wide"
)

# ────────────────────────────── DEBUG: Show errors instead of white screen ──────────────────────────────
st.markdown("**APP LOADED – Errors will show below**", unsafe_allow_html=True)

# ────────────────────────────── LOGGING ──────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ────────────────────────────── IMPORTS (Safe) ──────────────────────────────
try:
    from database import Database
    from ai_engine import AIEngine
    from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES
except Exception as e:
    st.error(f"IMPORT FAILED: {e}")
    st.stop()

# ────────────────────────────── CSS (unchanged) ──────────────────────────────
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
""", unsafe_allow_html=True)

# ────────────────────────────── INITIALIZERS ──────────────────────────────
@st.cache_resource
def init_db():
    try:
        db = Database()
        db.conn.execute("PRAGMA journal_mode=WAL;")
        return db
    except Exception as e:
        st.error(f"DB ERROR: {e}")
        class Dummy:
            def __getattr__(self, _): return lambda *a, **k: None
            def check_premium(self, _): return False
            def get_user(self, _): return {}
        return Dummy()

@st.cache_resource
def init_ai():
    try:
        key = st.secrets.get("GEMINI_API_KEY", "")
        return AIEngine(key) if key else AIEngine("")
    except Exception as e:
        st.error(f"AI ERROR: {e}")
        return AIEngine("")

db = init_db()
ai_engine = init_ai()

# ────────────────────────────── SESSION ──────────────────────────────
def init_session():
    defaults = {
        "logged_in": False, "user_id": None, "is_admin": False, "user": None,
        "show_welcome": True, "chat_history": [], "current_subject": "Mathematics",
        "is_parent": False
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

# ────────────────────────────── UI ──────────────────────────────
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
    totp = st.text_input("2FA (if enabled)", key="totp") if choice == "Login" else ""

    if st.button(choice):
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
                    st.rerun()
        except Exception as e:
            st.error(f"Login failed: {e}")

    st.info("**Demo:** `kingmumo15@gmail.com` / `@Yoounruly10`")

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
            badges = json.loads(user.get("badges", "[]"))
            for b in badges[:5]:
                st.markdown(f"**Trophy** {BADGES.get(b, b)}", unsafe_allow_html=True)
    except Exception as e:
        st.sidebar.error(f"Sidebar: {e}")

# ────────────────────────────── TABS ──────────────────────────────
def chat_tab():
    try:
        st.markdown("### Chat Tutor")
        if "chat_history" not in st.session_state: st.session_state.chat_history = []
        for msg in st.session_state.chat_history:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
        if prompt := st.chat_input("Ask..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    resp = ai_engine.generate_response(prompt, get_enhanced_prompt(st.session_state.current_subject, prompt))
                    st.markdown(resp)
                    st.session_state.chat_history.append({"role": "assistant", "content": resp})
            if hasattr(db, 'add_chat_history'): db.add_chat_history(st.session_state.user_id, st.session_state.current_subject, prompt, resp)
    except Exception as e:
        st.error(f"Chat: {e}")

def pdf_tab():
    try:
        st.markdown("### PDF Upload")
        uploaded = st.file_uploader("PDF", type="pdf")
        if uploaded:
            with st.spinner("Reading..."):
                text = ai_engine.extract_text_from_pdf(uploaded.read())
            st.text_area("Text:", text, height=300)
    except Exception as e:
        st.error(f"PDF: {e}")

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
        st.error(f"Exam: {e}")

# (Keep other tabs: essay_tab, premium_tab, etc. — simplified for brevity)

# ────────────────────────────── MAIN ──────────────────────────────
def main():
    try:
        init_session()
        if st.session_state.show_welcome:
            welcome_screen()
            return
        login_block()
        if not st.session_state.logged_in:
            st.info("Please log in.")
            return
        sidebar()
        tab1, tab2, tab3 = st.tabs(["Chat", "PDF", "Exam"])
        with tab1: chat_tab()
        with tab2: pdf_tab()
        with tab3: exam_tab()
    except Exception as e:
        st.error(f"**APP CRASHED**: {e}")
        logger.error(f"Crash: {e}", exc_info=True)

if __name__ == "__main__":
    main()
