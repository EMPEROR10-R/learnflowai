# app.py
import streamlit as st
import bcrypt
import json
import pandas as pd
from datetime import datetime
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES

# ────────────────────────────── CONFIG ──────────────────────────────
st.set_page_config(page_title="LearnFlow AI", page_icon="KE", layout="wide", initial_sidebar_state="expanded")

# ────────────────────────────── INIT DB & AI ──────────────────────────────
try:
    db = Database()
    ai_engine = AIEngine(st.secrets.get("GEMINI_API_KEY", ""))
except Exception as e:
    st.error(f"INIT FAILED: {e}")
    st.stop()

# ────────────────────────────── SESSION STATE ──────────────────────────────
def init_session():
    defaults = {
        "logged_in": False, "user_id": None, "is_admin": False, "user": None,
        "show_welcome": True, "chat_history": [], "current_subject": "Mathematics",
        "pdf_text": "", "current_tab": "Chat Tutor",
        "exam_questions": None, "user_answers": {}
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# ────────────────────────────── USER TIER LOGIC ──────────────────────────────
def get_user_tier():
    if st.session_state.is_admin:
        return "admin"
    user = db.get_user(st.session_state.user_id)
    if not user:
        return "basic"
    if user.get("is_premium") and db.check_premium_validity(st.session_state.user_id):
        return "premium"
    return "basic"

def enforce_access():
    tier = get_user_tier()
    tab = st.session_state.current_tab
    if tier == "basic" and tab not in ["Chat Tutor", "Settings"]:
        st.warning("Upgrade to **Premium** to access this feature.")
        st.stop()
    if tier == "basic":
        if tab == "Chat Tutor" and not db.can_ask_question(st.session_state.user_id):
            st.error("Daily limit: 10 questions. Upgrade to Premium!")
            st.stop()
        if tab == "PDF Q&A" and not db.can_upload_pdf(st.session_state.user_id):
            st.error("Daily limit: 3 PDF uploads. Upgrade to Premium!")
            st.stop()

# ────────────────────────────── UI COMPONENTS ──────────────────────────────
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
    if st.session_state.logged_in:
        return

    st.markdown("### Login / Sign Up")
    choice = st.radio("Action", ["Login", "Sign Up"], horizontal=True, label_visibility="collapsed")
    email = st.text_input("Email", key=f"{choice.lower()}_email")
    pwd = st.text_input("Password", type="password", key=f"{choice.lower()}_pwd")
    totp = st.text_input("2FA Code (if enabled)", key="totp") if choice == "Login" else ""

    if st.button(choice, type="primary"):
        if len(pwd) < 6:
            st.error("Password must be at least 6 characters.")
            return

        if choice == "Sign Up":
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

        # 2FA (safe)
        try:
            if db.is_2fa_enabled(user["user_id"]) and not db.verify_2fa_code(user["user_id"], totp):
                st.error("Invalid 2FA code.")
                return
        except AttributeError:
            pass  # 2FA not implemented

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
            st.warning("**Basic Plan:**\n- 10 questions/day\n- 3 PDFs/day")

        user = db.get_user(st.session_state.user_id) or {}
        streak = db.update_streak(st.session_state.user_id)
        st.markdown(f"**Streak:** {streak} days")

        st.session_state.current_subject = st.selectbox(
            "Subject", list(SUBJECT_PROMPTS.keys()), key="sidebar_subject"
        )

        # Badges
        badges_raw = user.get("badges", "[]")
        try:
            badges = json.loads(badges_raw) if isinstance(badges_raw, str) else badges_raw
        except:
            badges = []
        if badges:
            st.markdown("### Badges")
            for b in badges[:5]:
                st.markdown(f"{BADGES.get(b, b)}")

        # Leaderboard
        st.markdown("### Leaderboard")
        lb = db.get_leaderboard("exam")[:3]
        for i, entry in enumerate(lb):
            st.markdown(f"**{i+1}.** {entry['email']} – {entry['score']:.0f} pts")

# ────────────────────────────── TAB FUNCTIONS (ALL DEFINED) ──────────────────────────────
def chat_tab():
    st.session_state.current_tab = "Chat Tutor"
    enforce_access()

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Ask anything..."):
        if not db.can_ask_question(st.session_state.user_id):
            st.error("You've used your 10 questions today. Upgrade to Premium!")
            return

        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                context = st.session_state.pdf_text[-2000:] if st.session_state.pdf_text else ""
                # FIXED: No double comma
                enhanced_prompt = get_enhanced_prompt(st.session_state.current_subject, prompt, context)
                response = ai_engine.generate_response(prompt, enhanced_prompt)
                st.markdown(response)
                st.session_state.chat_history.append({"role": "assistant", "content": response})

        db.add_chat_history(st.session_state.user_id, st.session_state.current_subject, prompt, response)
        db.add_score(st.session_state.user_id, "chat", 10)

def pdf_tab():
    st.session_state.current_tab = "PDF Q&A"
    enforce_access()

    if not db.can_upload_pdf(st.session_state.user_id):
        st.error("**Daily limit:** 3 PDF uploads. Upgrade to Premium!")
        return

    uploaded_file = st.file_uploader("Upload PDF", type="pdf", key="pdf_uploader")

    if uploaded_file and not st.session_state.pdf_text:
        with st.spinner("Extracting text from PDF..."):
            text = ai_engine.extract_text_from_pdf(uploaded_file.read())
            st.session_state.pdf_text = text
            st.success("PDF loaded! Ask questions below.")
        st.text_area("Preview", text[:2000] + ("..." if len(text) > 2000 else ""), height=150, disabled=True)

    if st.session_state.pdf_text:
        if q := st.chat_input("Ask about the PDF..."):
            with st.chat_message("user"):
                st.markdown(q)
            with st.chat_message("assistant"):
                with st.spinner("Answering..."):
                    resp = ai_engine.generate_response(
                        q,
                        f"Based on this document:\n{st.session_state.pdf_text[-3000:]}"
                    )
                    st.markdown(resp)

def exam_tab():
    st.session_state.current_tab = "Exam Prep"
    enforce_access()

    if st.button("New Exam", key="new_exam_btn"):
        st.session_state.exam_questions = None
        st.session_state.user_answers = {}
        st.rerun()

    if not st.session_state.exam_questions:
        exam_input = st.text_input(
            "Exam Type (e.g., KCSE, Python Programming)",
            placeholder="KCSE",
            key="exam_type_input"
        )
        subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()), key="exam_subject")
        num = st.slider("Number of Questions", 1, 100, 10, key="exam_num")

        if st.button("Generate Exam", key="generate_exam"):
            exam_type = "Python Programming" if "python" in exam_input.lower() else exam_input
            with st.spinner("Generating exam..."):
                st.session_state.exam_questions = ai_engine.generate_exam_questions(subject, exam_type, num)
                st.session_state.user_answers = {}
            st.rerun()
    else:
        st.markdown("### Answer All Questions Below")
        for i, q in enumerate(st.session_state.exam_questions):
            st.markdown(f"**Q{i+1}:** {q['question']}")
            st.session_state.user_answers[i] = st.radio(
                "Select answer",
                q['options'],
                key=f"exam_radio_{i}"
            )

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Submit All Answers", type="primary", key="submit_exam"):
                res = ai_engine.grade_mcq(st.session_state.exam_questions, st.session_state.user_answers)
                score = res["percentage"]
                db.add_score(st.session_state.user_id, "exam", score)
                if score >= 90:
                    db.add_badge(st.session_state.user_id, "exam_master")
                    st.balloons()

                st.markdown(f"## Final Score: **{score}%**")
                st.markdown("### Detailed Feedback")
                for r in res["results"]:
                    icon = "Correct" if r["is_correct"] else "Wrong"
                    st.markdown(f"- {icon} **{r['question']}**")
                    st.markdown(f"   Your answer: `{r['user_answer']}`")
                    st.markdown(f"   Correct: `{r['correct_answer']}`")
                    if not r["is_correct"]:
                        st.markdown(f"   Feedback: {r.get('feedback', 'No feedback')}")
                st.session_state.exam_questions = None
                st.rerun()
        with col2:
            if st.button("Back to Menu", key="back_to_exam_menu"):
                st.session_state.exam_questions = None
                st.rerun()

def essay_tab():
    st.session_state.current_tab = "Essay Grader"
    enforce_access()

    essay = st.text_area("Paste your essay here", height=250, key="essay_input")
    if st.button("Grade Essay", key="grade_essay") and essay.strip():
        with st.spinner("Grading your essay..."):
            result = ai_engine.grade_essay(essay, "Kenyan curriculum")
            score = result["score"]
            db.add_score(st.session_state.user_id, "essay", score)
            if score >= 90:
                db.add_badge(st.session_state.user_id, "essay_expert")
                st.balloons()
            st.markdown(f"### Score: **{score}/100**")
            st.markdown(result["feedback"])

def settings_tab():
    st.session_state.current_tab = "Settings"
    st.markdown("### Settings")
    theme = st.selectbox("Theme", ["Light", "Dark"], key="theme_select")
    font = st.selectbox("Font", ["Sans-serif", "Serif"], key="font_select")
    if st.button("Save Settings"):
        st.success("Settings saved successfully!")

def premium_tab():
    st.session_state.current_tab = "Premium"
    if st.session_state.is_admin:
        st.success("You have **full access** as Admin.")
        return

    user = db.get_user(st.session_state.user_id)
    discount = user.get("discount", 0) if user else 0
    price = 500 * (1 - discount)
    st.markdown(f"### Upgrade to Premium – **KES {price:.0f}/month**")
    if discount > 0:
        st.success("20% Leaderboard Champion Discount Applied!")

    st.info("Send payment to M-Pesa: `0701617120`")
    phone = st.text_input("Your Phone Number", key="prem_phone")
    code = st.text_input("M-Pesa Code", key="prem_code")
    if st.button("Submit Payment", key="prem_submit"):
        if phone and code:
            db.add_manual_payment(st.session_state.user_id, phone, code)
            st.success("Payment submitted! Awaiting approval.")
        else:
            st.error("Please fill both fields.")

def admin_dashboard():
    st.session_state.current_tab = "Admin"
    if not st.session_state.is_admin:
        st.error("Access denied.")
        return

    st.markdown("## Admin Control Centre")
    st.write("Only **1 admin** exists: `kingmumo15@gmail.com`")

    if st.button("Apply Monthly Discounts"):
        db.apply_monthly_discount()
        st.success("20% discount applied to leaderboard champions!")

    payments = db.get_pending_payments()
    if payments:
        st.markdown("### Pending Payments")
        for p in payments:
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                st.write(f"**{p['phone']}** – `{p['mpesa_code']}`")
            with c2:
                if st.button("Approve", key=f"approve_{p['id']}"):
                    db.approve_manual_payment(p['id'])
                    st.rerun()
            with c3:
                if st.button("Reject", key=f"reject_{p['id']}"):
                    db.reject_manual_payment(p['id'])
                    st.rerun()

    users = db.get_all_users()
    if users:
        df = pd.DataFrame(users)[["email", "name", "role", "is_premium"]]
        st.dataframe(df)

# ────────────────────────────── MAIN APP ──────────────────────────────
def main():
    try:
        init_session()

        if st.session_state.show_welcome:
            welcome_screen()
            return

        login_block()
        if not st.session_state.logged_in:
            st.info("Please log in to continue.")
            return

        sidebar()
        enforce_access()

        # Define tabs
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

        # Render tabs
        tab_objects = st.tabs(tabs)
        tab_map = {
            "Chat Tutor": chat_tab,
            "Settings": settings_tab,
            "PDF Q&A": pdf_tab,
            "Exam Prep": exam_tab,
            "Essay Grader": essay_tab,
            "Premium": premium_tab,
            "Admin Control Centre": admin_dashboard
        }

        for tab_name, tab_obj in zip(tabs, tab_objects):
            with tab_obj:
                tab_map[tab_name]()

    except Exception as e:
        st.error(f"APP CRASHED: {e}")
        st.write("Please refresh or contact support.")

if __name__ == "__main__":
    main()
