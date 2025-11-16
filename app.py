# app.py
import streamlit as st
import bcrypt
import json
import pandas as pd
import plotly.express as px
from datetime import datetime, date, timedelta
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES

# ==============================================================================
# GAMIFICATION: LEVELS (DEFINED HERE – NOT IN PROMPTS.PY)
# ==============================================================================
LEVELS = {
    1: 0, 2: 100, 3: 250, 4: 500, 5: 1000,
    6: 2000, 7: 3500, 8: 6000, 9: 10000, 10: 15000
}

# ────────────────────────────── MUST BE FIRST ──────────────────────────────
st.set_page_config(
    page_title="LearnFlow AI",
    page_icon="KE",
    layout="wide",
    initial_sidebar_state="expanded"
)

# HIDE ALL STREAMLIT & GIT ICONS
hide_streamlit_style = """
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .css-1d391kg, .css-1v0mbdj, .css-1y0t9e2, .css-1q8ddts, .css-1v3fvcr, .css-1x8cf1d {display: none;}
    .css-18e3th9 {padding-top: 0rem; padding-left: 1rem; padding-right: 1rem;}
    .css-1v3fvcr a[href*="streamlit"], 
    .css-1d391kg a[href*="github"], 
    .css-1v0mbdj a[href*="github"],
    .css-1y0t9e2 a[href*="github"] {display: none !important;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# INIT
try:
    db = Database()
    ai_engine = AIEngine(st.secrets.get("GEMINI_API_KEY", ""))
except Exception as e:
    st.error(f"INIT FAILED: {e}")
    st.stop()

# SESSION STATE
def init_session():
    defaults = {
        "logged_in": False, "user_id": None, "is_admin": False, "user": None,
        "show_welcome": True, "chat_history": [], "current_subject": "Mathematics",
        "pdf_text": "", "current_tab": "Chat Tutor",
        "exam_questions": None, "user_answers": {}, "exam_submitted": False,
        "reset_user_id": None, "reset_otp": None, "reset_step": 0
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# USER TIER
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
    if tier == "admin": return
    if tier == "basic" and tab not in ["Chat Tutor", "Progress", "Settings"]:
        st.warning("Upgrade to **Premium** to access this feature.")
        st.stop()
    if tier == "basic":
        if tab == "Chat Tutor" and db.get_daily_question_count(st.session_state.user_id) >= 10:
            st.error("You've used your **10 questions** today. Upgrade to Premium!")
            st.stop()
        if tab == "PDF Q&A" and db.get_daily_pdf_count(st.session_state.user_id) >= 3:
            st.error("You've used your **3 PDF uploads** today. Upgrade to Premium!")
            st.stop()

# GAMIFICATION
def get_user_level(user):
    xp = user.get("total_xp", 0)
    for level, req in reversed(LEVELS.items()):
        if xp >= req:
            return level, xp - req, LEVELS.get(level + 1, float('inf')) - req
    return 1, xp, 100

def award_xp(user_id, points, reason):
    db.add_xp(user_id, points)
    st.success(f"+{points} XP – {reason}")

# UI
def welcome_screen():
    st.markdown("""
    <div style="background:linear-gradient(135deg,#009E60,#FFD700);padding:60px;border-radius:20px;text-align:center;color:white">
        <h1>LearnFlow AI</h1>
        <p style="font-size:1.2rem">Your Kenyan AI Tutor</p>
        <p style="font-size:1.1rem">KCPE • KPSEA • KJSEA • KCSE • Python</p>
        <p style="font-size:1rem">Earn XP • Level Up • Unlock Badges</p>
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
    choice = st.radio("Action", ["Login", "Sign Up", "Forgot Password"], horizontal=True, label_visibility="collapsed")
    
    if choice == "Forgot Password":
        email = st.text_input("Enter your email")
        if st.button("Send Reset Code"):
            user = db.get_user_by_email(email)
            if user and db.is_2fa_enabled(user["user_id"]):
                otp = db.generate_otp(user["user_id"])
                st.session_state.reset_user_id = user["user_id"]
                st.session_state.reset_step = 1
                st.success("2FA code sent to your authenticator!")
            else:
                st.error("No 2FA-enabled account found.")
        if st.session_state.reset_step == 1:
            code = st.text_input("Enter 2FA Code")
            if st.button("Verify"):
                if db.verify_2fa_code(st.session_state.reset_user_id, code):
                    st.session_state.reset_step = 2
                else:
                    st.error("Invalid code.")
        if st.session_state.reset_step == 2:
            new_pwd = st.text_input("New Password", type="password")
            confirm = st.text_input("Confirm Password", type="password")
            if st.button("Reset Password"):
                if new_pwd == confirm and len(new_pwd) >= 6:
                    db.update_password(st.session_state.reset_user_id, new_pwd)
                    st.success("Password reset! Please log in.")
                    st.session_state.reset_step = 0
                    st.rerun()
                else:
                    st.error("Passwords must match and be ≥6 chars.")
        return

    email = st.text_input("Email", key=f"{choice.lower()}_email")
    pwd = st.text_input("Password", type="password", key=f"{choice.lower()}_pwd")
    totp = st.text_input("2FA Code (if enabled)", key="totp") if choice == "Login" else ""

    if st.button(choice, type="primary"):
        if choice == "Sign Up":
            if len(pwd) < 6:
                st.error("Password must be ≥6 characters.")
                return
            uid = db.create_user(email, pwd)
            if uid:
                db.add_xp(uid, 50)
                st.success("Account created! +50 XP")
            else:
                st.error("Email already exists.")
            return

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

        if db.is_2fa_enabled(user["user_id"]) and not db.verify_2fa_code(user["user_id"], totp):
            st.error("Invalid 2FA code.")
            return

        db.update_user_activity(user["user_id"])
        st.session_state.update({
            "logged_in": True, "user_id": user["user_id"], "is_admin": user["role"] == "admin", "user": user
        })
        st.success("Login successful!")
        st.rerun()

def sidebar():
    with st.sidebar:
        st.markdown("## LearnFlow AI")
        tier = get_user_tier()
        st.markdown(f"**Tier:** `{tier.upper()}`")
        if tier == "basic":
            q = 10 - db.get_daily_question_count(st.session_state.user_id)
            p = 3 - db.get_daily_pdf_count(st.session_state.user_id)
            st.warning(f"**Basic:** {q}Q | {p}PDF left")

        user = st.session_state.user
        level, current_xp, next_xp = get_user_level(user)
        st.markdown(f"### Level {level}")
        st.progress(current_xp / next_xp if next_xp else 1)
        st.caption(f"{current_xp}/{next_xp} XP")

        streak = db.update_streak(st.session_state.user_id)
        st.markdown(f"**Streak:** {streak} days")

        st.session_state.current_subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))

        badges = json.loads(user.get("badges", "[]"))
        if badges:
            st.markdown("### Badges")
            for b in badges[:5]:
                st.markdown(f"{BADGES.get(b, b)}")

        st.markdown("### Leaderboard")
        lb = db.get_leaderboard("exam")[:3]
        for i, e in enumerate(lb):
            st.markdown(f"**{i+1}.** {e['email']} – {e['score']:.0f}")

# TABS
def chat_tab():
    st.session_state.current_tab = "Chat Tutor"
    enforce_access()
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    if prompt := st.chat_input("Ask anything..."):
        if db.get_daily_question_count(st.session_state.user_id) >= 10:
            st.error("Daily limit reached.")
            return
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                context = st.session_state.pdf_text[-2000:] if st.session_state.pdf_text else ""
                enhanced = get_enhanced_prompt(st.session_state.current_subject, prompt, context)
                resp = ai_engine.generate_response(prompt, enhanced)
                st.markdown(resp)
                st.session_state.chat_history.append({"role": "assistant", "content": resp})
        db.add_chat_history(st.session_state.user_id, st.session_state.current_subject, prompt, resp)
        db.add_score(st.session_state.user_id, "chat", 10)
        award_xp(st.session_state.user_id, 10, "Asked a question")

def pdf_tab():
    st.session_state.current_tab = "PDF Q&A"
    enforce_access()
    remaining = 3 - db.get_daily_pdf_count(st.session_state.user_id)
    if remaining <= 0:
        st.error("PDF limit reached. Upgrade!")
        return
    st.info(f"**{remaining} PDF uploads left**")
    file = st.file_uploader("Upload PDF", type="pdf")
    if file and not st.session_state.pdf_text:
        with st.spinner("Reading..."):
            text = ai_engine.extract_text_from_pdf(file.read())
            st.session_state.pdf_text = text
            st.success("PDF loaded!")
            award_xp(st.session_state.user_id, 30, "Uploaded PDF")
    if st.session_state.pdf_text and (q := st.chat_input("Ask about PDF...")):
        with st.chat_message("user"): st.markdown(q)
        with st.chat_message("assistant"):
            with st.spinner("Answering..."):
                resp = ai_engine.generate_response(q, f"Text:\n{st.session_state.pdf_text[-3000:]}")
                st.markdown(resp)
                award_xp(st.session_state.user_id, 15, "PDF Q&A")

def exam_tab():
    st.session_state.current_tab = "Exam Prep"
    enforce_access()
    if st.session_state.exam_submitted:
        if st.button("New Exam"):
            st.session_state.exam_questions = None
            st.session_state.user_answers = {}
            st.session_state.exam_submitted = False
            st.rerun()
    if not st.session_state.exam_questions:
        exam_type = st.selectbox("Exam Type", list(EXAM_TYPES.keys()))
        subject = st.selectbox("Subject", EXAM_TYPES[exam_type]["subjects"])
        num = st.slider("Questions", 1, 100, 10)
        if st.button("Generate Exam"):
            st.session_state.exam_questions = ai_engine.generate_exam_questions(subject, exam_type, num)
            st.rerun()
    else:
        for i, q in enumerate(st.session_state.exam_questions):
            st.markdown(f"**Q{i+1}:** {q['question']}")
            st.session_state.user_answers[i] = st.radio("Choose", q['options'], key=f"ans_{i}")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Submit All", type="primary"):
                res = ai_engine.grade_mcq(st.session_state.exam_questions, st.session_state.user_answers)
                score = res["percentage"]
                db.add_score(st.session_state.user_id, "exam", score)
                if score >= 90: db.add_badge(st.session_state.user_id, "perfect_score")
                st.markdown(f"## Score: {score}%")
                for r in res["results"]:
                    icon = "Correct" if r["is_correct"] else "Wrong"
                    st.markdown(f"- {icon} **{r['question']}**  \n  Your: `{r['user_answer']}`  \n  Correct: `{r['correct_answer']}`")
                xp = int(score / 10)
                award_xp(st.session_state.user_id, xp, f"Exam {score}%")
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
        if score >= 90: db.add_badge(st.session_state.user_id, "perfect_score")
        st.markdown(f"**Score: {score}/100** – {res['feedback']}")
        award_xp(st.session_state.user_id, int(score / 5), f"Essay {score}/100")

def progress_tab():
    st.session_state.current_tab = "Progress"
    st.markdown("## Your Learning Journey")

    user = st.session_state.user
    level, current_xp, next_xp = get_user_level(user)
    st.markdown(f"### Level {level}")
    st.progress(current_xp / next_xp if next_xp else 1)
    st.caption(f"**{current_xp}/{next_xp} XP** to next level")

    scores = db.get_user_scores(st.session_state.user_id)
    if scores:
        df = pd.DataFrame(scores)
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.date
        fig = px.line(df, x="timestamp", y="score", color="category", title="Score Progress")
        st.plotly_chart(fig, use_container_width=True)

    subject_scores = db.get_subject_performance(st.session_state.user_id)
    if subject_scores:
        df_sub = pd.DataFrame(subject_scores)
        fig2 = px.bar(df_sub, x="subject", y="avg_score", title="Average Score by Subject")
        st.plotly_chart(fig2, use_container_width=True)

def settings_tab():
    st.session_state.current_tab = "Settings"
    st.markdown("### Settings")
    st.selectbox("Theme", ["Light", "Dark"], key="theme")
    st.selectbox("Font", ["Sans-serif", "Serif", "Monospace"], key="font")

    st.markdown("### 2FA (Authenticator)")
    if not db.is_2fa_enabled(st.session_state.user_id):
        if st.button("Enable 2FA"):
            secret = db.enable_2fa(st.session_state.user_id)
            qr = db.get_2fa_qr(st.session_state.user_id)
            st.image(qr, caption="Scan with Google Authenticator")
            st.code(secret, language="text")
            st.info("Backup this secret key!")
            award_xp(st.session_state.user_id, 20, "Enabled 2FA")
    else:
        st.success("2FA Enabled")
        if st.button("Disable 2FA"):
            db.disable_2fa(st.session_state.user_id)
            st.success("2FA Disabled")

    st.markdown("### Chat History")
    history = db.get_chat_history(st.session_state.user_id)
    for h in history[-5:]:
        with st.expander(f"{h['subject']} – {h['timestamp'][:10]}"):
            st.write(f"**Q:** {h['user_query']}")
            st.write(f"**A:** {h['ai_response']}")

def premium_tab():
    st.session_state.current_tab = "Premium"
    if st.session_state.is_admin:
        st.success("Admin has full access.")
        return
    discount = st.session_state.user.get("discount", 0) if st.session_state.user else 0
    price = 500 * (1 - discount)
    st.markdown(f"### Upgrade – **KES {price:.0f}/month**")
    if discount: st.success("20% Champion Discount!")
    st.info("Send to M-Pesa: `0701617120`")
    phone = st.text_input("Phone")
    code = st.text_input("M-Pesa Code")
    if st.button("Submit Payment"):
        db.add_manual_payment(st.session_state.user_id, phone, code)
        st.success("Submitted!")

def admin_dashboard():
    st.session_state.current_tab = "Admin"
    if not st.session_state.is_admin: st.error("Access denied."); return
    st.markdown("## Admin Control Centre")
    users = db.get_all_users()
    df = pd.DataFrame(users)
    edited = st.data_editor(df)
    for _, row in edited.iterrows():
        c1, c2, c3 = st.columns(3)
        with c1: st.button(f"Ban {row['email']}", key=f"ban_{row['user_id']}", on_click=db.ban_user, args=(row['user_id'],))
        with c2: st.button(f"Upgrade {row['email']}", key=f"up_{row['user_id']}", on_click=db.upgrade_to_premium, args=(row['user_id'],))
        with c3: st.button(f"Downgrade {row['email']}", key=f"down_{row['user_id']}", on_click=db.downgrade_to_basic, args=(row['user_id'],))
    st.markdown("### Payments")
    for p in db.get_pending_payments():
        c1, c2, c3, c4 = st.columns([2,2,1,1])
        with c1: st.write(p['phone'])
        with c2: st.write(p['mpesa_code'])
        with c3: st.button("Approve", key=f"a{p['id']}", on_click=db.approve_manual_payment, args=(p['id'],))
        with c4: st.button("Reject", key=f"r{p['id']}", on_click=db.reject_manual_payment, args=(p['id'],))

# MAIN
def main():
    try:
        init_session()
        if st.session_state.show_welcome: welcome_screen(); return
        login_block()
        if not st.session_state.logged_in: st.info("Log in."); return
        sidebar()
        enforce_access()
        tabs = ["Chat Tutor", "Progress", "Settings"]  # FIXED: Removed 'drying' typo
        if get_user_tier() in ["premium", "admin"]:
            tabs += ["PDF Q&A", "Exam Prep", "Essay Grader"]
        if get_user_tier() == "basic":
            tabs.append("Premium")
        if st.session_state.is_admin:
            tabs.append("Admin Control Centre")
        tab_objs = st.tabs(tabs)
        tab_map = {
            "Chat Tutor": chat_tab, "Progress": progress_tab, "Settings": settings_tab,
            "PDF Q&A": pdf_tab, "Exam Prep": exam_tab, "Essay Grader": essay_tab,
            "Premium": premium_tab, "Admin Control Centre": admin_dashboard
        }
        for name, obj in zip(tabs, tab_objs):
            with obj:
                tab_map[name]()
    except Exception as e:
        st.error(f"CRASH: {e}")

if __name__ == "__main__":
    main()
