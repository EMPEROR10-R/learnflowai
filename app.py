# app.py
import streamlit as st
import bcrypt
import json
import pandas as pd
from datetime import datetime
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES

# HIDE STREAMLIT UI (Git, Fork, 3 dots, Rerun, Settings, Print, About, Streamlit logo)
hide_streamlit_style = """
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .css-1d391kg {display: none;}  /* GitHub icon */
    .css-1v0mbdj {display: none;}  /* Fork */
    .css-1y0t9e2 {display: none;}  /* 3 dots */
    .css-1q8ddts {display: none;}  /* Rerun */
    .css-1v3fvcr {display: none;}  /* Settings */
    .css-1x8cf1d {display: none;}  /* Print */
    .css-1v3fvcr a {display: none;} /* About */
    .css-18e3th9 {padding-top: 0rem; padding-left: 1rem; padding-right: 1rem;}
    .css-1d391kg a {display: none;} /* Streamlit link */
    .css-1v0mbdj a {display: none;}
    .css-1y0t9e2 a {display: none;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

st.set_page_config(page_title="LearnFlow AI", page_icon="KE", layout="wide", initial_sidebar_state="expanded")

# INIT
try:
    db = Database()
    ai_engine = AIEngine(st.secrets.get("GEMINI_API_KEY", ""))
except Exception as e:
    st.error(f"INIT FAILED: {e}")
    st.stop()

# SESSION
def init_session():
    defaults = {
        "logged_in": False, "user_id": None, "is_admin": False, "user": None,
        "show_welcome": True, "chat_history": [], "current_subject": "Mathematics",
        "pdf_text": "", "current_tab": "Chat Tutor",
        "exam_questions": None, "user_answers": {}, "exam_submitted": False
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

# TIER
def get_user_tier():
    if st.session_state.is_admin: return "admin"
    user = db.get_user(st.session_state.user_id)
    if not user: return "basic"
    if user.get("is_premium") and db.check_premium_validity(st.session_state.user_id):
        return "premium"
    return "basic"

def enforce_access():
    tier = get_user_tier()
    tab = st.session_state.current_tab

    # ADMIN HAS FULL ACCESS
    if tier == "admin":
        return

    if tier == "basic" and tab not in ["Chat Tutor", "Settings"]:
        st.warning("Upgrade to **Premium** to access this feature.")
        st.stop()

    if tier == "basic":
        if tab == "Chat Tutor" and not db.can_ask_question(st.session_state.user_id):
            remaining = 10 - db.get_daily_question_count(st.session_state.user_id)
            if remaining <= 0:
                st.error("You've used your **10 questions** today. Upgrade to Premium for unlimited!")
            else:
                st.warning(f"You have **{remaining} questions** left today.")
            st.stop()
        if tab == "PDF Q&A" and not db.can_upload_pdf(st.session_state.user_id):
            remaining = 3 - db.get_daily_pdf_count(st.session_state.user_id)
            if remaining <= 0:
                st.error("You've used your **3 PDF uploads** today. Upgrade to Premium!")
            else:
                st.warning(f"You have **{remaining} PDF uploads** left today.")
            st.stop()

# UI
def welcome_screen():
    st.markdown("""
    <div style="background:linear-gradient(135deg,#009E60,#FFD700);padding:60px;border-radius:20px;text-align:center;color:white">
        <h1>LearnFlow AI</h1>
        <p style="font-size:1.2rem">Your Kenyan AI Tutor</p>
        <p style="font-size:1rem">KCPE • KPSEA • KJSEA • KCSE • Python Programming</p>
    </div>
    """, unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
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
        if choice == "Sign Up":
            if len(pwd) < 6:
                st.error("Password must be **at least 6 characters**.")
                return
            uid = db.create_user(email, pwd)
            if uid:
                st.success("Account created! Please log in.")
            else:
                st.error("Email already exists.")
            return

        # LOGIN
        user = db.get_user_by_email(email)
        if not user:
            st.error("Invalid email or password.")
            return

        stored_hash = user["password_hash"]
        if isinstance(stored_hash, str):
            stored_hash = stored_hash.encode('utf-8')
        if not bcrypt.checkpw(pwd.encode('utf-8'), stored_hash):
            st.error("Invalid email or password.")
            return

        try:
            if db.is_2fa_enabled(user["user_id"]) and not db.verify_2fa_code(user["user_id"], totp):
                st.error("Invalid 2FA code.")
                return
        except: pass

        db.update_user_activity(user["user_id"])
        st.session_state.update({
            "logged_in": True,
            "user_id": user["user_id"],
            "is_admin": user["role"] == "admin",
            "user": user
        })
        st.success("Login successful!")
        st.rerun()

def sidebar():
    with st.sidebar:
        st.markdown("## LearnFlow AI")
        tier = get_user_tier()
        st.markdown(f"**Tier:** `{tier.upper()}`")
        if tier == "basic":
            q_left = 10 - db.get_daily_question_count(st.session_state.user_id)
            p_left = 3 - db.get_daily_pdf_count(st.session_state.user_id)
            st.warning(f"**Basic Plan:**\n- {q_left} questions left\n- {p_left} PDFs left")

        user = db.get_user(st.session_state.user_id) or {}
        streak = db.update_streak(st.session_state.user_id)
        st.markdown(f"**Streak:** {streak} days")

        st.session_state.current_subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()), key="subj")

        badges_raw = user.get("badges", "[]")
        try: badges = json.loads(badges_raw) if isinstance(badges_raw, str) else badges_raw
        except: badges = []
        if badges:
            st.markdown("### Badges")
            for b in badges[:5]: st.markdown(f"{BADGES.get(b, b)}")

        st.markdown("### Leaderboard")
        lb = db.get_leaderboard("exam")[:3]
        for i, e in enumerate(lb): st.markdown(f"**{i+1}.** {e['email']} – {e['score']:.0f}")

# TABS
def chat_tab():
    st.session_state.current_tab = "Chat Tutor"
    enforce_access()
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
    if prompt := st.chat_input("Ask anything..."):
        if not db.can_ask_question(st.session_state.user_id):
            st.error("Daily limit reached.")
            return
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                context = st.session_state.pdf_text[-2000:] if st.session_state.pdf_text else ""
                enhanced_prompt = get_enhanced_prompt(st.session_state.current_subject, prompt, context)
                resp = ai_engine.generate_response(prompt, enhanced_prompt)
                st.markdown(resp)
                st.session_state.chat_history.append({"role": "assistant", "content": resp})
        db.add_chat_history(st.session_state.user_id, st.session_state.current_subject, prompt, resp)
        db.add_score(st.session_state.user_id, "chat", 10)

def pdf_tab():
    st.session_state.current_tab = "PDF Q&A"
    enforce_access()
    if not db.can_upload_pdf(st.session_state.user_id):
        remaining = 3 - db.get_daily_pdf_count(st.session_state.user_id)
        if remaining <= 0:
            st.error("You've used your **3 PDF uploads** today. Upgrade to Premium!")
        else:
            st.warning(f"You have **{remaining} PDF uploads** left today.")
        return
    file = st.file_uploader("Upload PDF", type="pdf")
    if file and not st.session_state.pdf_text:
        with st.spinner("Reading..."):
            text = ai_engine.extract_text_from_pdf(file.read())
            st.session_state.pdf_text = text
            st.success("PDF loaded!")
    if st.session_state.pdf_text:
        if q := st.chat_input("Ask about PDF..."):
            with st.chat_message("user"): st.markdown(q)
            with st.chat_message("assistant"):
                with st.spinner("Answering..."):
                    resp = ai_engine.generate_response(q, f"Text:\n{st.session_state.pdf_text[-3000:]}")
                    st.markdown(resp)

def exam_tab():
    st.session_state.current_tab = "Exam Prep"
    enforce_access()

    if st.session_state.exam_submitted:
        if st.button("New Exam", key="new_exam_after"):
            st.session_state.exam_questions = None
            st.session_state.user_answers = {}
            st.session_state.exam_submitted = False
            st.rerun()

    if not st.session_state.exam_questions:
        exam_type = st.selectbox("Exam Type", list(EXAM_TYPES.keys()), key="exam_type_select")
        subject = st.selectbox("Subject", EXAM_TYPES[exam_type]["subjects"], key="exam_subject")
        num = st.slider("Questions", 1, 100, 10)
        if st.button("Generate Exam"):
            st.session_state.exam_questions = ai_engine.generate_exam_questions(subject, exam_type, num)
            st.session_state.user_answers = {}
            st.rerun()
    else:
        st.markdown("### Answer All Questions")
        for i, q in enumerate(st.session_state.exam_questions):
            st.markdown(f"**Q{i+1}:** {q['question']}")
            st.session_state.user_answers[i] = st.radio("Choose", q['options'], key=f"ans_{i}")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Submit All", type="primary"):
                res = ai_engine.grade_mcq(st.session_state.exam_questions, st.session_state.user_answers)
                score = res["percentage"]
                db.add_score(st.session_state.user_id, "exam", score)
                if score >= 90: db.add_badge(st.session_state.user_id, "exam_master")
                st.markdown(f"## Score: {score}%")
                for r in res["results"]:
                    icon = "Correct" if r["is_correct"] else "Wrong"
                    st.markdown(f"- {icon} **{r['question']}**  \n  Your: `{r['user_answer']}`  \n  Correct: `{r['correct_answer']}`")
                st.session_state.exam_submitted = True
                st.rerun()
        with col2:
            if st.button("Cancel"):
                st.session_state.exam_questions = None
                st.rerun()

def essay_tab():
    st.session_state.current_tab = "Essay Grader"
    enforce_access()
    essay = st.text_area("Essay", height=200)
    if st.button("Grade") and essay.strip():
        res = ai_engine.grade_essay(essay, "Kenyan curriculum")
        score = res["score"]
        db.add_score(st.session_state.user_id, "essay", score)
        if score >= 90: db.add_badge(st.session_state.user_id, "essay_expert")
        st.markdown(f"**Score: {score}/100** – {res['feedback']}")

def settings_tab():
    st.session_state.current_tab = "Settings"
    st.markdown("### Settings")

    # Theme
    theme = st.selectbox("Theme", ["Light", "Dark"], key="theme")

    # Font
    fonts = ["Sans-serif", "Serif", "Monospace", "Arial", "Courier New", "Georgia", "Times New Roman", "Verdana"]
    st.selectbox("Font", fonts, key="font")

    # 2FA
    st.markdown("### 2FA")
    if st.button("Enable 2FA"):
        secret = db.enable_2fa(st.session_state.user_id)
        qr = db.get_2fa_qr(st.session_state.user_id)
        st.image(qr)
        st.code(secret)
    if db.is_2fa_enabled(st.session_state.user_id):
        if st.button("Disable 2FA"):
            db.disable_2fa(st.session_state.user_id)
            st.success("2FA Disabled")

    # History
    st.markdown("### Chat History")
    history = db.get_chat_history(st.session_state.user_id)
    for h in history[-10:]:
        st.markdown(f"**{h['subject']}**: {h['user_query'][:50]}...")

def premium_tab():
    st.session_state.current_tab = "Premium"
    if st.session_state.is_admin:
        st.success("Admin has full access.")
        return
    user = db.get_user(st.session_state.user_id)
    discount = user.get("discount", 0) if user else 0
    price = 500 * (1 - discount)
    st.markdown(f"### Price: **KES {price:.0f}**")
    if discount: st.success("20% Discount!")
    st.info("Send to M-Pesa: `0701617120`")
    phone = st.text_input("Phone", key="pphone")
    code = st.text_input("Code", key="pcode")
    if st.button("Submit"):
        db.add_manual_payment(st.session_state.user_id, phone, code)
        st.success("Submitted!")

def admin_dashboard():
    st.session_state.current_tab = "Admin"
    if not st.session_state.is_admin:
        st.error("Access denied.")
        return

    st.markdown("## Admin Control Centre")

    # Users Table
    users = db.get_all_users()
    df = pd.DataFrame(users)
    edited = st.data_editor(df, num_rows="dynamic")

    # Ban / Upgrade
    for idx, row in edited.iterrows():
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button(f"Ban {row['email']}", key=f"ban_{row['user_id']}"):
                db.ban_user(row['user_id'])
        with col2:
            if st.button(f"Upgrade {row['email']}", key=f"up_{row['user_id']}"):
                db.upgrade_to_premium(row['user_id'])
        with col3:
            if st.button(f"Downgrade {row['email']}", key=f"down_{row['user_id']}"):
                db.downgrade_to_basic(row['user_id'])

    # Pending Payments
    st.markdown("### Pending Payments")
    payments = db.get_pending_payments()
    if payments:
        for p in payments:
            c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
            with c1: st.write(f"**Phone:** {p['phone']}")
            with c2: st.write(f"**Code:** `{p['mpesa_code']}`")
            with c3:
                if st.button("Approve", key=f"a{p['id']}"):
                    db.approve_manual_payment(p['id'])
                    st.rerun()
            with c4:
                if st.button("Reject", key=f"r{p['id']}"):
                    db.reject_manual_payment(p['id'])
                    st.rerun()

# MAIN
def main():
    try:
        init_session()
        if st.session_state.show_welcome: welcome_screen(); return
        login_block()
        if not st.session_state.logged_in: st.info("Log in."); return
        sidebar()
        enforce_access()

        base_tabs = ["Chat Tutor", "Settings"]
        premium_tabs = ["PDF Q&A", "Exam Prep", "Essay Grader"]
        tabs = base_tabs.copy()
        tier = get_user_tier()
        if tier in ["premium", "admin"]:
            tabs.extend(premium_tabs)
        if tier == "basic":
            tabs.append("Premium")
        if st.session_state.is_admin:
            tabs.append("Admin Control Centre")

        tab_objs = st.tabs(tabs)
        tab_map = {
            "Chat Tutor": chat_tab,
            "Settings": settings_tab,
            "PDF Q&A": pdf_tab,
            "Exam Prep": exam_tab,
            "Essay Grader": essay_tab,
            "Premium": premium_tab,
            "Admin Control Centre": admin_dashboard
        }
        for tab_name, tab_obj in zip(tabs, tab_objs):
            with tab_obj:
                tab_map[tab_name]()
    except Exception as e:
        st.error(f"CRASH: {e}")

if __name__ == "__main__":
    main()
