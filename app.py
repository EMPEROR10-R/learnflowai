# app.py
import streamlit as st
import os
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
import json
import time
import uuid
import smtplib
import random
import pandas as pd
import pyotp
import qrcode
from io import BytesIO
from database import Database
from ai_engine import AIEngine
from utils import Translator_Utils, EssayGrader, VoiceInputHelper
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES
import streamlit.components.v1 as components

# ----------------------------------------------------------------------
# Page config & CSS
# ----------------------------------------------------------------------
st.set_page_config(
    page_title="LearnFlow AI - Kenyan AI Tutor (KCPE, KPSEA, KJSEA, KCSE)",
    page_icon="Kenya",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @keyframes fadeInDown { from {opacity:0; transform:translateY(-30px);} to {opacity:1; transform:translateY(0);} }
    @keyframes slideInLeft { from {opacity:0; transform:translateX(-50px);} to {opacity:1; transform:translateX(0);} }
    @keyframes slideInRight { from {opacity:0; transform:translateX(50px);} to {opacity:1; transform:translateX(0);} }
    @keyframes pulse { 0%,100% {transform:scale(1);} 50% {transform:scale(1.05);} }
    @keyframes glow { 0%,100% {box-shadow:0 0 5px rgba(102,126,234,0.5);} 50% {box-shadow:0 0 20px rgba(102,126,234,0.8);} }
    @keyframes gradient-shift { 0% {background-position:0% 50%;} 50% {background-position:100% 50%;} 100% {background-position:0% 50%;} }
    .main-header {font-size:2.5rem; font-weight:bold;
        background:linear-gradient(135deg,#009E60 0%,#FFD700 50%,#CE1126 100%);
        background-size:200% 200%; -webkit-background-clip:text; -webkit-text-fill-color:transparent;
        text-align:center; margin-bottom:1rem;
        animation:fadeInDown 1s ease-out, gradient-shift 3s ease infinite;}
    .chat-message-user {background:#E8F5E9; padding:15px; border-radius:15px; margin:10px 0;
        border-left:4px solid #4CAF50; animation:slideInRight .5s ease-out;}
    .chat-message-ai {background:#E3F2FD; padding:15px; border-radius:15px; margin:10px 0;
        border-left:4px solid #2196F3; animation:slideInLeft .5s ease-out;}
    .streak-badge {display:inline-block; padding:5px 15px;
        background:linear-gradient(135deg,#FF6B6B 0%,#FFE66D 100%); border-radius:20px;
        color:white; font-weight:bold; margin:5px; animation:pulse 2s ease-in-out infinite;}
    .premium-badge {background:linear-gradient(135deg,#FFD700 0%,#FFA500 100%);
        padding:3px 10px; border-radius:10px; color:white; font-size:.8rem; font-weight:bold;
        animation:glow 2s ease-in-out infinite;}
    .stButton>button {width:100%; transition:all .3s ease;}
    .stButton>button:hover {transform:translateY(-2px); box-shadow:0 5px 15px rgba(0,158,96,.4);}
    .welcome-animation {animation:fadeInDown 1.2s ease-out;}
    .metric-card {animation:fadeInDown .8s ease-out;}
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------------------
# Cached resources
# ----------------------------------------------------------------------
@st.cache_resource
def init_database() -> Database:
    return Database()

@st.cache_resource
def init_translator() -> Translator_Utils:
    return Translator_Utils()

@st.cache_resource
def init_ai_engine() -> AIEngine:
    gemini_key = st.secrets.get("GEMINI_API_KEY", "")
    hf_key = st.secrets.get("HF_API_KEY", "")
    return AIEngine(gemini_key, hf_key)

db = init_database()
ai_engine = init_ai_engine()
translator = init_translator()

# ----------------------------------------------------------------------
# Session-state helpers
# ----------------------------------------------------------------------
def init_session_state():
    defaults = {
        "chat_history": [], "current_subject": "Mathematics", "language": "en",
        "show_voice_button": True, "show_welcome": True, "logged_in": False,
        "is_admin": False, "is_parent": False, "manual_approved": False
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# ----------------------------------------------------------------------
# Streak & limits
# ----------------------------------------------------------------------
def check_and_update_streak():
    streak = db.update_streak(st.session_state.user_id)
    if streak == 3: db.add_badge(st.session_state.user_id, "streak_3")
    elif streak == 7: db.add_badge(st.session_state.user_id, "streak_7")
    elif streak == 30: db.add_badge(st.session_state.user_id, "streak_30")
    return streak

def check_premium_limits() -> dict:
    is_premium = db.check_premium(st.session_state.user_id)
    if is_premium:
        return {"can_query": True, "can_upload_pdf": True,
                "queries_left": "Unlimited", "pdfs_left": "Unlimited", "is_premium": True}
    queries = db.get_daily_query_count(st.session_state.user_id)
    pdfs = db.get_pdf_count_today(st.session_state.user_id)
    return {
        "can_query": queries < 10,
        "can_upload_pdf": pdfs < 1,
        "queries_left": max(0, 10 - queries),
        "pdfs_left": max(0, 1 - pdfs),
        "is_premium": False,
    }

# ----------------------------------------------------------------------
# Sidebar
# ----------------------------------------------------------------------
def sidebar_config():
    with st.sidebar:
        st.markdown('<p class="main-header">LearnFlow AI</p>', unsafe_allow_html=True)
        limits = check_premium_limits()
        if limits["is_premium"]:
            st.markdown('<span class="premium-badge">PREMIUM</span>', unsafe_allow_html=True)
        streak = check_and_update_streak()
        st.markdown(f'<span class="streak-badge">{streak} Day Streak</span>', unsafe_allow_html=True)

        user = db.get_user(st.session_state.user_id)
        if user and user.get("badges"):
            badges = json.loads(user["badges"])
            if badges:
                st.write("**Badges:**")
                st.write(" ".join([BADGES.get(b, b) for b in badges[:5]]))

        st.markdown("---")
        st.markdown("### Settings")
        subjects = list(SUBJECT_PROMPTS.keys())
        idx = subjects.index(st.session_state.current_subject) if st.session_state.current_subject in subjects else 0
        st.session_state.current_subject = st.selectbox("Choose subject", subjects, index=idx)

        lang_map = {v: k for k, v in translator.supported_languages.items()}
        sel_lang = st.selectbox("Interface Language", list(lang_map.keys()), index=0)
        st.session_state.language = lang_map[sel_lang]

        st.markdown("---")
        if not limits["is_premium"]:
            st.markdown("### Daily Limits (Free)")
            st.metric("AI Queries Left", f"{limits['queries_left']}/10")
            st.metric("PDF Uploads Left", f"{limits['pdfs_left']}/1")
            if st.button("Upgrade to Premium", type="primary"):
                st.session_state.show_premium = True

        st.markdown("---")
        st.caption("KCPE • KPSEA • KJSEA • KCSE Ready")

# ----------------------------------------------------------------------
# Tabs
# ----------------------------------------------------------------------
def main_chat_interface():
    limits = check_premium_limits()
    st.markdown(f'<h1 class="main-header">{st.session_state.current_subject} Tutor</h1>', unsafe_allow_html=True)

    for msg in st.session_state.chat_history:
        cls = "chat-message-user" if msg["role"] == "user" else "chat-message-ai"
        role = "You" if msg["role"] == "user" else "AI Tutor"
        st.markdown(f'<div class="{cls}"><strong>{role}:</strong> {msg["content"]}</div>', unsafe_allow_html=True)

    user_question = st.text_area(
        "Ask your question (I'll give hints, not direct answers):",
        height=100, key="user_input",
        placeholder="e.g. Explain photosynthesis in simple terms…"
    )
    col_v1, _ = st.columns([1, 4])
    with col_v1:
        if st.button("Voice Input"):
            components.html(VoiceInputHelper.get_voice_input_html(), height=120)

    if st.button("Send Question", type="primary"):
        if not user_question.strip():
            return
        if not limits["can_query"]:
            st.error("Daily query limit reached! Upgrade for unlimited.")
            return

        st.session_state.chat_history.append({"role": "user", "content": user_question})
        with st.spinner("Thinking…"):
            system_prompt = get_enhanced_prompt(
                st.session_state.current_subject,
                user_question,
                f"Previous messages: {len(st.session_state.chat_history)}"
            )
            response = ""
            placeholder = st.empty()
            for chunk in ai_engine.stream_response(user_question, system_prompt):
                response += chunk
                placeholder.markdown(f'<div class="chat-message-ai"><strong>AI Tutor:</strong> {response}</div>', unsafe_allow_html=True)

        st.session_state.chat_history.append({"role": "assistant", "content": response})
        db.add_chat_history(
            st.session_state.user_id,
            st.session_state.current_subject,
            user_question,
            response
        )
        db.update_user_activity(st.session_state.user_id)
        if len(st.session_state.chat_history) == 2:
            db.add_badge(st.session_state.user_id, "first_question")
            st.balloons()
        st.rerun()

def pdf_upload_tab():
    limits = check_premium_limits()
    st.markdown("### Upload Notes / PDFs")
    if not limits["can_upload_pdf"]:
        st.warning("Daily PDF limit reached!")
        return
    uploaded = st.file_uploader("Choose a PDF", type=["pdf"])
    if uploaded:
        with st.spinner("Extracting text…"):
            txt = ai_engine.extract_text_from_pdf(uploaded.read())
        st.success(f"Extracted {len(txt)} characters")
        with st.expander("Raw Text (Debug)"):
            st.code(txt[:2000] + ("..." if len(txt) > 2000 else ""))
        db.add_pdf_upload(st.session_state.user_id, uploaded.name)
        db.add_badge(st.session_state.user_id, "pdf_explorer")
        q = st.text_area("Ask about this PDF", placeholder="e.g. What is the main topic?")
        if st.button("Ask"):
            if not q.strip():
                st.warning("Please ask a question.")
                return
            with st.spinner("Analyzing…"):
                prompt = f"Document:\n{txt[:3000]}\n\nQuestion: {q}"
                resp = ai_engine.generate_response(prompt, "Answer in 1-3 short sentences.")
                st.markdown(f'<div class="chat-message-ai"><strong>AI Tutor:</strong> {resp}</div>', unsafe_allow_html=True)
                db.add_chat_history(st.session_state.user_id, "PDF", q, resp)

def progress_dashboard_tab():
    user = db.get_user(st.session_state.user_id)
    if not user:
        st.info("No data yet.")
        return
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Questions", user.get("total_queries", 0))
    c2.metric("Streak", f"{user.get('streak_days', 0)} days")
    badges = json.loads(user.get("badges", "[]"))
    c3.metric("Badges", len(badges))
    c4.metric("Status", "Premium" if db.check_premium(st.session_state.user_id) else "Free")

def exam_mode_tab():
    limits = check_premium_limits()
    st.markdown("### Exam Prep Mode")
    exam = st.selectbox("Select Exam", list(EXAM_TYPES.keys()),
                        format_func=lambda x: f"{x} – {EXAM_TYPES[x]['description']}")
    info = EXAM_TYPES[exam]
    st.info(info["description"])
    subject = st.selectbox("Subject", info["subjects"])
    num_questions = st.slider("Number of Questions", 1, 10, 5)
    if st.button("Generate Practice Questions", type="primary"):
        if not limits["can_query"]:
            st.error("Query limit reached.")
            return
        with st.spinner("Generating…"):
            prompt = f"Generate {num_questions} {exam} practice questions in {subject}. Include 4 options (A-D), one correct answer, and a brief explanation. Use Kenyan curriculum style."
            resp = ai_engine.generate_response(prompt, "You are an expert Kenyan exam generator. Output clean markdown.")
            st.markdown(resp)
            db.add_chat_history(st.session_state.user_id, f"{exam} Practice",
                                f"Generate {num_questions} Qs in {subject}", resp)

    st.markdown("### Self-Score")
    score = st.slider("How many did you get right?", 0, num_questions, 0, key="score_slider")
    if st.button("Submit Score"):
        pct = score / num_questions * 100
        if pct >= 80:
            st.success(f"**{pct:.0f}% – Excellent!**")
            db.add_badge(st.session_state.user_id, "quiz_ace")
            st.balloons()
        elif pct >= 60:
            st.info(f"**{pct:.0f}% – Good!**")
        else:
            st.warning(f"**{pct:.0f}% – Review {subject}**")
        db.add_quiz_result(st.session_state.user_id, subject, exam, score, num_questions)

def essay_grader_tab():
    st.markdown("### AI Essay Grader")
    essay = st.text_area("Paste your essay here", height=300)
    if st.button("Grade Essay"):
        if not essay.strip():
            st.warning("Please enter your essay.")
            return
        with st.spinner("Grading…"):
            grader = EssayGrader()
            res = grader.grade_essay(essay)
            st.markdown(f"**Score:** {res['total_score']}/100 – {res['overall']}")
            for cat, sc in res["breakdown"].items():
                st.write(f"- **{cat.title()}**: {sc}/100")
            st.write("**Stats**")
            col1, col2, col3 = st.columns(3)
            col1.metric("Words", res["stats"]["word_count"])
            col2.metric("Sentences", res["stats"]["sentence_count"])
            col3.metric("Paragraphs", res["stats"]["paragraph_count"])

# ----------------------------------------------------------------------
# Premium Tab – Manual Upgrade (no Stripe)
# ----------------------------------------------------------------------
def premium_tab():
    st.markdown("### Premium Plan")
    if db.check_premium(st.session_state.user_id):
        st.success("You are a **Premium** member!")
        st.balloons()
        return

    st.info("""
    **How to upgrade manually**

    1. Send **KSh 500** to M-Pesa: **254712345678**  
    2. Use **Reference**: Your email (`{email}`)  
    3. Fill the form below with the **phone used** and the **M-Pesa code** from the SMS.
    """.format(email=st.session_state.user_email))

    col1, col2 = st.columns(2)
    with col1:
        phone = st.text_input("Phone used", placeholder="2547...")
    with col2:
        mpesa_code = st.text_input("M-Pesa Code", placeholder="e.g. RA12B34C5D")

    if st.button("Submit Proof", type="primary"):
        if not phone or not mpesa_code:
            st.error("Both fields required.")
        elif len(mpesa_code) != 10 or not mpesa_code.isalnum():
            st.error("M-Pesa code must be 10 characters.")
        else:
            db.add_manual_payment(st.session_state.user_id, phone, mpesa_code)
            st.success("Submitted! Admin will verify shortly.")
            st.balloons()

# ----------------------------------------------------------------------
# Settings Tab – 2FA + Parent Link
# ----------------------------------------------------------------------
def settings_tab():
    st.header("Settings")

    # 2FA
    st.subheader("Two-Factor Authentication")
    if db.is_2fa_enabled(st.session_state.user_id):
        st.success("2FA Enabled")
        if st.button("Disable 2FA"):
            conn = db.get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET two_fa_secret = NULL WHERE user_id = ?", (st.session_state.user_id,))
            conn.commit()
            conn.close()
            st.success("2FA disabled.")
            st.rerun()
    else:
        st.info("Enable 2FA (free with Google Authenticator)")
        if st.button("Enable 2FA"):
            secret = db.generate_2fa_secret(st.session_state.user_id)
            uri = pyotp.TOTP(secret).provisioning_uri(name=st.session_state.user_email, issuer_name="LearnFlow AI")
            qr = qrcode.make(uri)
            buf = BytesIO()
            qr.save(buf, format="PNG")
            st.image(buf.getvalue(), caption="Scan with Authenticator")
            st.code(secret)

    # Parent Link (for child)
    if not st.session_state.is_parent and not st.session_state.is_admin:
        st.subheader("Link Parent")
        parent_email = st.text_input("Parent Email")
        parent_pass = st.text_input("Parent Password", type="password")
        if st.button("Link Parent"):
            msg = db.link_parent(st.session_state.user_id, parent_email, parent_pass)
            st.write(msg)

# ----------------------------------------------------------------------
# Parent Dashboard
# ----------------------------------------------------------------------
def parent_dashboard():
    st.header("Parent Dashboard")
    children = db.get_children(st.session_state.user_id)
    if not children:
        st.info("No children linked.")
        return

    for child in children:
        with st.expander(f"**{child['name'] or child['email']}**"):
            activity = db.get_user_activity(child["user_id"], 7)
            if activity:
                df = pd.DataFrame(activity)
                df["date"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d")
                daily = df.groupby("date").agg({"duration_minutes": "sum", "action": "count"}).rename(columns={"action": "sessions"})
                st.bar_chart(daily["duration_minutes"])
                st.write("**Last 7 Days:**", daily)
            else:
                st.write("No activity yet.")

            st.write("**Quiz Rankings**")
            for subject in SUBJECT_PROMPTS.keys():
                rankings = db.get_subject_rankings(subject)
                if not rankings.empty and child["name"] in rankings["user"].values:
                    rank = rankings[rankings["user"] == child["name"]].index[0] + 1
                    score = rankings[rankings["user"] == child["name"]]["avg_score"].values[0]
                    st.write(f"**{subject}**: Rank #{rank} – {score}%")

# ----------------------------------------------------------------------
# Admin Dashboard (manual approvals)
# ----------------------------------------------------------------------
def admin_dashboard():
    if not st.session_state.is_admin:
        st.error("Access denied.")
        return
    st.markdown("## Admin Dashboard")
    users = db.get_all_users()
    df = pd.DataFrame(users)
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d")
        st.dataframe(df, use_container_width=True)

    st.markdown("### Pending Manual Payments")
    pending = db.get_pending_manual_payments()
    if pending:
        for row in pending:
            col1, col2, col3 = st.columns([4, 1, 1])
            with col1:
                st.write(f"**{row['name'] or row['email']}**")
                st.caption(f"Phone: {row['phone']} | Code: `{row['mpesa_code']}`")
            with col2:
                if st.button("Approve", key=f"app_{row['id']}"):
                    if db.approve_manual_payment(row["id"]):
                        st.success("Premium granted!")
                        st.rerun()
            with col3:
                if st.button("Reject", key=f"rej_{row['id']}", type="secondary"):
                    db.reject_manual_payment(row["id"])
                    st.warning("Rejected.")
                    st.rerun()
    else:
        st.info("No pending requests.")

    if users:
        selected_uid = st.selectbox("Toggle Premium (override)", df["user_id"],
            format_func=lambda x: next(u["email"] for u in users if u["user_id"] == x))
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Toggle Premium"):
                db.toggle_premium(selected_uid)
                st.success("Toggled.")
                st.rerun()

# ----------------------------------------------------------------------
# Login / Signup
# ----------------------------------------------------------------------
def login_signup_block():
    if st.session_state.logged_in:
        return

    st.markdown("### Login or Sign Up")
    choice = st.radio("Choose", ["Login", "Sign Up"], horizontal=True)

    if choice == "Sign Up":
        email = st.text_input("Email")
        pwd = st.text_input("Password", type="password")
        if st.button("Create Account"):
            if not email or "@" not in email:
                st.error("Valid email required.")
            elif not pwd:
                st.error("Password required.")
            elif db.get_user_by_email(email):
                st.error("Email already taken.")
            else:
                uid = db.create_user(email, pwd)
                st.session_state.user_id = uid
                st.session_state.user_email = email
                st.session_state.logged_in = True
                st.success("Account created!")
                st.rerun()
    else:
        email = st.text_input("Email", key="login_email")
        pwd = st.text_input("Password", type="password", key="login_pwd")
        totp = st.text_input("2FA Code (if enabled)")

        if st.button("Login"):
            success, msg, _ = login_user(email, pwd, totp)
            st.write(msg)
            if success:
                st.rerun()

    st.stop()

def login_user(email: str, password: str, totp_code: str = ""):
    user = db.get_user_by_email(email)
    if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return False, "Invalid credentials.", None

    if db.is_2fa_enabled(user["user_id"]):
        if not totp_code:
            return False, "2FA code required.", "2fa_needed"
        if not db.verify_2fa_code(user["user_id"], totp_code):
            return False, "Invalid 2FA code.", None

    st.session_state.update({
        "user_id": user["user_id"],
        "user_name": user.get("name", ""),
        "user_email": email,
        "is_admin": user["role"] == "admin",
        "is_parent": bool(db.get_children(user["user_id"])),
        "logged_in": True
    })
    db.update_user_activity(user["user_id"])
    db.log_activity(user["user_id"], "login")
    return True, "Logged in!", None

# ----------------------------------------------------------------------
# Welcome animation
# ----------------------------------------------------------------------
def show_welcome_animation():
    if st.session_state.get("show_welcome", True):
        st.markdown("""
        <div class="welcome-animation" style="background:linear-gradient(135deg,#009E60,#FFD700); padding:40px; border-radius:20px; text-align:center; color:white; margin:20px 0; box-shadow:0 10px 30px rgba(0,0,0,.2);">
            <h1 style="font-size:3rem; margin:0;">LearnFlow AI</h1>
            <p style="font-size:1.5rem;">Your Kenyan AI Tutor</p>
            <p>KCPE • KPSEA • KJSEA • KCSE Ready</p>
        </div>
        """, unsafe_allow_html=True)
        _, col, _ = st.columns([1, 1, 1])
        with col:
            if st.button("Start Learning!", type="primary", use_container_width=True):
                st.session_state.show_welcome = False
                st.rerun()

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    init_session_state()

    # Fresh manual-payment approval check
    if st.session_state.logged_in and not db.check_premium(st.session_state.user_id):
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM manual_payments 
            WHERE user_id = ? AND status = 'approved' 
            AND processed_at > datetime('now', '-1 minute')
        """, (st.session_state.user_id,))
        if cursor.fetchone():
            st.success("Payment verified! You are now **Premium**.")
            st.balloons()
            st.rerun()

    if st.session_state.show_welcome:
        show_welcome_animation()
        return

    login_signup_block()
    sidebar_config()

    # Build tabs
    base_tabs = ["Chat Tutor", "PDF Upload", "Progress", "Exam Prep", "Essay Grader", "Premium", "Settings"]
    extra = []
    if st.session_state.is_parent:
        extra.append("Parent Dashboard")
    if st.session_state.is_admin:
        extra.append("Admin Dashboard")
    tabs = st.tabs(base_tabs + extra)

    with tabs[0]: main_chat_interface()
    with tabs[1]: pdf_upload_tab()
    with tabs[2]: progress_dashboard_tab()
    with tabs[3]: exam_mode_tab()
    with tabs[4]: essay_grader_tab()
    with tabs[5]: premium_tab()
    with tabs[6]: settings_tab()
    if st.session_state.is_parent and len(tabs) > 7:
        with tabs[7]: parent_dashboard()
    if st.session_state.is_admin and len(tabs) > (8 if st.session_state.is_parent else 7):
        with tabs[-1]: admin_dashboard()

    st.caption("LearnFlow AI – KCPE • KPSEA • KJSEA • KCSE")

if __name__ == "__main__":
    main()
