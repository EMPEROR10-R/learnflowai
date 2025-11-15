# app.py
import streamlit as st
import bcrypt
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES
import json

# ---------- CONFIG ----------
st.set_page_config(page_title="LearnFlow AI", page_icon="KE", layout="wide")

# ---------- INITIALISE ----------
db = Database()
ai_engine = AIEngine(st.secrets.get("GEMINI_API_KEY", ""))

# ---------- SESSION ----------
def init_session():
    defaults = {
        "logged_in": False, "user_id": None, "is_admin": False, "user": None,
        "show_welcome": True, "chat_history": [], "current_subject": "Mathematics",
        "is_parent": False
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# ---------- UI ----------
def welcome_screen():
    st.markdown('<div style="background:linear-gradient(135deg,#009E60,#FFD700);padding:50px;border-radius:20px;color:white;text-align:center">'
                '<h1>LearnFlow AI</h1><p>Your Kenyan AI Tutor</p><p>KCPE • KPSEA • KJSEA • KCSE</p></div>', unsafe_allow_html=True)
    _, col, _ = st.columns([1, 1, 1])
    with col:
        if st.button("Start Learning!", type="primary", use_container_width=True):
            st.session_state.show_welcome = False
            st.rerun()

def login_block():
    if st.session_state.logged_in:
        return
    st.markdown("### Login / Sign Up")
    choice = st.radio("Action", ["Login", "Sign Up"], horizontal=True, label_visibility="collapsed")
    email = st.text_input("Email", key=f"{choice.lower()}_email")
    pwd = st.text_input("Password", type="password", key=f"{choice.lower()}_pwd")
    totp = st.text_input("2FA Code (if enabled)", key="totp") if choice == "Login" else ""

    if st.button(choice, type="primary"):
        if len(pwd) < 6:
            st.error("Password must be ≥6 characters")
        elif choice == "Sign Up":
            uid = db.create_user(email, pwd)
            st.success("Account created! Please log in.") if uid else st.error("Email already taken")
        else:
            user = db.get_user_by_email(email)
            if not user or not bcrypt.checkpw(pwd.encode('utf-8'), user["password_hash"].encode('utf-8')):
                st.error("Invalid email or password")
            elif db.is_2fa_enabled(user["user_id"]) and not db.verify_2fa_code(user["user_id"], totp):
                st.error("Invalid 2FA code")
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
        user = db.get_user(st.session_state.user_id)
        if user and user.get("profile_pic"):
            st.image(user["profile_pic"], width=100)
        if db.check_premium(st.session_state.user_id):
            st.markdown('<span style="background:#FFD700;color:#000;padding:4px 10px;border-radius:12px;font-weight:bold">PREMIUM</span>', unsafe_allow_html=True)
        streak = db.update_streak(st.session_state.user_id)
        st.markdown(f'<span style="background:linear-gradient(135deg,#FF6B6B,#FFE66D);padding:6px 14px;border-radius:20px;color:white;font-weight:bold">Streak: {streak} days</span>', unsafe_allow_html=True)
        st.session_state.current_subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))
        badges = json.loads(user.get("badges", "[]"))
        for b in badges[:5]:
            st.markdown(f"**Trophy** {BADGES.get(b, b)}", unsafe_allow_html=True)

# ---------- TABS ----------
def chat_tab():
    st.markdown("### Chat Tutor")
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    if prompt := st.chat_input("Ask anything..."):
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
    file = st.file_uploader("Choose PDF", type="pdf")
    if file:
        with st.spinner("Extracting..."):
            text = ai_engine.extract_text_from_pdf(file.read())
        st.text_area("Extracted Text", text, height=300)

def exam_tab():
    st.markdown("### Exam Prep")
    if "exam_questions" not in st.session_state:
        subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))
        num = st.number_input("Questions", 1, 20, 5)
        if st.button("Generate"):
            st.session_state.exam_questions = ai_engine.generate_exam_questions(subject, "KCSE", num)
            st.session_state.user_answers = {}
            st.rerun()
    else:
        for i, q in enumerate(st.session_state.exam_questions):
            st.markdown(f"**Q{i+1}:** {q['question']}")
            st.session_state.user_answers[i] = st.radio("Choose", q['options'], key=f"ans{i}")
        if st.button("Submit"):
            res = ai_engine.grade_mcq(st.session_state.exam_questions, st.session_state.user_answers)
            db.add_score(st.session_state.user_id, "exam", res["percentage"])
            st.markdown(f"**Score: {res['percentage']}%**")
            for r in res["results"]:
                icon = "Correct" if r["is_correct"] else "Wrong"
                st.markdown(f"- {icon} **{r['question']}**")
            del st.session_state.exam_questions, st.session_state.user_answers

def essay_tab():
    st.markdown("### Essay Grader")
    essay = st.text_area("Paste your essay", height=200)
    if st.button("Grade") and essay.strip():
        with st.spinner("Grading..."):
            res = ai_engine.grade_essay(essay, "Kenyan curriculum")
            db.add_score(st.session_state.user_id, "essay", res["score"])
            st.markdown(f"**Score: {res['score']}/100** – {res['feedback']}")

def premium_tab():
    st.markdown("### Premium – KES 500/month")
    st.info("Send to M-Pesa: `0701617120`")
    phone = st.text_input("Phone")
    code = st.text_input("M-Pesa Code")
    if st.button("Submit"):
        if phone and code:
            db.add_manual_payment(st.session_state.user_id, phone, code)
            st.success("Submitted!")
        else:
            st.error("Fill both fields")

# ---------- MAIN ----------
def main():
    init_session()
    if st.session_state.show_welcome:
        welcome_screen()
        return
    login_block()
    if not st.session_state.logged_in:
        st.info("Please log in.")
        return
    sidebar()
    tabs = ["Chat Tutor", "PDF Upload", "Exam Prep", "Essay Grader"]
    if not db.check_premium(st.session_state.user_id):
        tabs.append("Premium")
    if st.session_state.is_admin:
        tabs.append("Admin")
    tab_objs = st.tabs(tabs)
    with tab_objs[0]: chat_tab()
    with tab_objs[1]: pdf_tab()
    with tab_objs[2]: exam_tab()
    with tab_objs[3]: essay_tab()
    if "Premium" in tabs:
        with tab_objs[tabs.index("Premium")]: premium_tab()
    if st.session_state.is_admin:
        with tab_objs[tabs.index("Admin")]: st.write("Admin panel coming soon.")

if __name__ == "__main__":
    main()
