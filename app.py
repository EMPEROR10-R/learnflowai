# app.py
import streamlit as st
import bcrypt
import json
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES

# ────────────────────────────── CONFIG ──────────────────────────────
st.set_page_config(page_title="LearnFlow AI", page_icon="KE", layout="wide")

# ────────────────────────────── INIT ──────────────────────────────
try:
    db = Database()
    ai_engine = AIEngine(st.secrets.get("GEMINI_API_KEY", ""))
except Exception as e:
    st.error(f"INIT FAILED: {e}")
    st.stop()

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
    st.markdown('<div style="background:linear-gradient(135deg,#009E60,#FFD700);padding:50px;border-radius:20px;color:white;text-align:center">'
                '<h1>LearnFlow AI</h1><p>Your Kenyan AI Tutor</p><p>KCPE • KPSEA • KJSEA • KCSE</p></div>', unsafe_allow_html=True)
    _, c, _ = st.columns([1,1,1])
    with c:
        if st.button("Start Learning!", type="primary", use_container_width=True):
            st.session_state.show_welcome = False
            st.rerun()

def login_block():
    if st.session_state.logged_in: return
    st.markdown("### Login / Sign Up")
    choice = st.radio("Action", ["Login", "Sign Up"], horizontal=True, label_visibility="collapsed")
    email = st.text_input("Email", key=f"{choice.lower()}_email")
    pwd = st.text_input("Password", type="password", key=f"{choice.lower()}_pwd")
    totp = st.text_input("2FA Code (if enabled)", key="totp") if choice == "Login" else ""

    if st.button(choice, type="primary"):
        if len(pwd) < 6:
            st.error("Password ≥6 chars")
        elif choice == "Sign Up":
            uid = db.create_user(email, pwd)
            st.success("Created! Log in.") if uid else st.error("Email taken")
        else:
            user = db.get_user_by_email(email)
            if not user or not bcrypt.checkpw(pwd.encode(), user["password_hash"].encode()):
                st.error("Wrong credentials")
            elif db.is_2fa_enabled(user["user_id"]) and not db.verify_2fa_code(user["user_id"], totp):
                st.error("Bad 2FA")
            else:
                db.update_user_activity(user["user_id"])
                st.session_state.update({
                    "logged_in": True, "user_id": user["user_id"],
                    "is_admin": user["role"] == "admin", "user": user,
                    "is_parent": bool(user.get("parent_id"))
                })
                st.rerun()

def sidebar():
    with st.sidebar:
        st.markdown("## LearnFlow AI")
        user = db.get_user(st.session_state.user_id) or {}
        if user.get("profile_pic"):
            st.image(user["profile_pic"], width=100)
        if db.check_premium(st.session_state.user_id):
            st.markdown('<span style="background:#FFD700;color:#000;padding:4px 10px;border-radius:12px;font-weight:bold">PREMIUM</span>', unsafe_allow_html=True)
        streak = db.update_streak(st.session_state.user_id)
        st.markdown(f'<span style="background:linear-gradient(135deg,#FF6B6B,#FFE66D);padding:6px 14px;border-radius:20px;color:white;font-weight:bold">Streak: {streak} days</span>', unsafe_allow_html=True)

        # FIXED: Unique key for selectbox
        st.session_state.current_subject = st.selectbox(
            "Subject", list(SUBJECT_PROMPTS.keys()), key="sidebar_subject_select"
        )

        st.markdown("### Badges")
        badges_raw = user.get("badges", "[]")
        try:
            badges = json.loads(badges_raw) if isinstance(badges_raw, str) else (badges_raw or [])
        except:
            badges = []
        for b in badges[:5]:
            st.markdown(f"**Trophy** {BADGES.get(b, b)}", unsafe_allow_html=True)

# ────────────────────────────── TABS ──────────────────────────────
def chat_tab():
    st.markdown("### Chat Tutor")
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
    if prompt := st.chat_input("Ask..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                resp = ai_engine.generate_response(prompt, get_enhanced_prompt(st.session_state.current_subject, prompt, ""))
                st.markdown(resp)
                st.session_state.chat_history.append({"role": "assistant", "content": resp})
        db.add_chat_history(st.session_state.user_id, st.session_state.current_subject, prompt, resp)
        db.add_score(st.session_state.user_id, "chat", 10)

def pdf_tab():
    st.markdown("### PDF Upload")
    file = st.file_uploader("PDF", type="pdf", key="pdf_upload")
    if file:
        with st.spinner("Reading..."):
            text = ai_engine.extract_text_from_pdf(file.read())
        st.text_area("Text:", text, height=300, key="pdf_text")

def exam_tab():
    st.markdown("### Exam Prep")
    if "exam_questions" not in st.session_state:
        # FIXED: Unique keys
        subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()), key="exam_subject_select")
        num = st.number_input("Questions", 1, 10, 5, key="exam_num_questions")
        if st.button("Generate", key="generate_exam"):
            st.session_state.exam_questions = ai_engine.generate_exam_questions(subject, "KCSE", num)
            st.session_state.user_answers = {}
            st.rerun()
    else:
        for i, q in enumerate(st.session_state.exam_questions):
            st.markdown(f"**Q{i+1}:** {q['question']}")
            st.session_state.user_answers[i] = st.radio("Choose", q['options'], key=f"exam_ans_{i}")
        if st.button("Submit", key="submit_exam"):
            res = ai_engine.grade_mcq(st.session_state.exam_questions, st.session_state.user_answers)
            db.add_score(st.session_state.user_id, "exam", res["percentage"])
            st.markdown(f"**Score: {res['percentage']}%**")
            for r in res["results"]:
                icon = "Correct" if r["is_correct"] else "Wrong"
                st.markdown(f"- {icon} **{r['question']}**")
            del st.session_state.exam_questions, st.session_state.user_answers

def essay_tab():
    st.markdown("### Essay Grader")
    essay = st.text_area("Paste your essay", height=200, key="essay_input")
    if st.button("Grade", key="grade_essay") and essay.strip():
        with st.spinner("Grading..."):
            res = ai_engine.grade_essay(essay, "Kenyan curriculum")
            db.add_score(st.session_state.user_id, "essay", res["score"])
            st.markdown(f"**Score: {res['score']}/100** – {res['feedback']}")

def premium_tab():
    st.markdown("### Premium – KES 500/month")
    st.info("Send to M-Pesa: `0701617120`")
    phone = st.text_input("Phone", key="premium_phone")
    code = st.text_input("M-Pesa Code", key="premium_code")
    if st.button("Submit", key="submit_premium"):
        if phone and code:
            db.add_manual_payment(st.session_state.user_id, phone, code)
            st.success("Submitted!")
        else:
            st.error("Fill both fields")

def progress_tab():
    st.markdown("### Progress")
    st.write("Coming soon.")

def settings_tab():
    st.markdown("### Settings")
    st.write("Theme, 2FA – coming soon.")

def parent_dashboard():
    st.markdown("### Parent Dashboard")
    st.write("Track child – coming soon.")

def admin_dashboard():
    if not st.session_state.is_admin:
        st.error("Access denied")
        return
    st.markdown("## Admin Control Centre")
    st.write("Manage users, payments, analytics – coming soon.")
    users = db.get_all_users() if hasattr(db, 'get_all_users') else []
    if users:
        df = pd.DataFrame(users)
        st.dataframe(df[["email", "name", "role", "is_premium"]])

# ────────────────────────────── MAIN ──────────────────────────────
def main():
    try:
        init_session()
        if st.session_state.show_welcome:
            welcome_screen()
            return
        login_block()
        if not st.session_state.logged_in:
            st.info("Log in to continue.")
            return
        sidebar()

        # ALL FEATURES RESTORED
        tabs = ["Chat Tutor", "PDF Upload", "Progress", "Exam Prep", "Essay Grader", "Settings"]
        if not db.check_premium(st.session_state.user_id):
            tabs.insert(5, "Premium")
        if st.session_state.is_parent:
            tabs.append("Parent Dashboard")
        if st.session_state.is_admin:
            tabs.append("Admin Control Centre")

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
        if st.session_state.is_admin and "Admin Control Centre" in tabs:
            with tab_objs[tabs.index("Admin Control Centre")]: admin_dashboard()

    except Exception as e:
        st.error(f"APP CRASHED: {e}")

if __name__ == "__main__":
    main()
