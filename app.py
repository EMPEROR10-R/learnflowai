# app.py
import streamlit as st
import pyotp, qrcode, bcrypt, json
from io import BytesIO
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES
import pandas as pd
from datetime import datetime, date, timedelta

st.set_page_config(page_title="LearnFlow AI", page_icon="Kenya", layout="wide")

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
    .card {background:#fff; padding:15px; border-radius:12px; box-shadow:0 2px 6px rgba(0,0,0,0.1); margin:10px 0;}
    .premium-header {font-size:1.6rem; font-weight:bold; color:#FFD700; text-align:center;}
</style>
""", unsafe_allow_html=True)

# ────────────────────────────── INITIALISERS ──────────────────────────────
@st.cache_resource
def init_db():
    try:
        return Database()
    except Exception as e:
        st.error("Database error – see logs.")
        print(e)
        class Dummy:
            def __getattr__(self, _): return lambda *a, **k: None
            def get_leaderboard(self, _): return []
            def check_premium(self, _): return False
        return Dummy()

@st.cache_resource
def init_ai():
    try:
        key = st.secrets.get("GEMINI_API_KEY", "")
        return AIEngine(key)
    except Exception as e:
        print(e)
        return AIEngine("")

db = init_db()
ai_engine = init_ai()

# ────────────────────────────── SESSION STATE ──────────────────────────────
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
    if st.session_state.theme == "dark":
        css += "body{background:#222;color:#eee;}"
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

# ────────────────────────────── HELPERS ──────────────────────────────
def qr_image(email, secret):
    uri = pyotp.TOTP(secret).provisioning_uri(email, "LearnFlow AI")
    qr = qrcode.make(uri)
    buf = BytesIO()
    qr.save(buf, "PNG")
    return buf.getvalue()

def login_user(email, pwd, totp=""):
    if "@" not in email: return False, "Invalid email", None
    user = db.get_user_by_email(email)
    if not user or not bcrypt.checkpw(pwd.encode(), user["password_hash"].encode()):
        return False, "Wrong credentials", None
    if db.is_2fa_enabled(user["user_id"]) and not db.verify_2fa_code(user["user_id"], totp):
        return False, "Bad 2FA code", None
    db.update_user_activity(user["user_id"])
    return True, "Logged in!", user

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
            ok, msg, u = login_user(email, pwd, totp)
            st.write(msg)
            if ok:
                st.session_state.update({
                    "logged_in": True, "user_id": u["user_id"],
                    "is_admin": u["role"]=="admin", "user": u,
                    "is_parent": bool(u.get("parent_id"))
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
        db.add_score(st.session_state.user_id, "chat", 1)
        st.rerun()

def pdf_tab():
    st.markdown('<span class="tab-header">### PDF Upload & Analysis</span>', unsafe_allow_html=True)
    up = st.file_uploader("Upload PDF", type="pdf")
    if up:
        txt = ai_engine.extract_text_from_pdf(up.read())
        st.success(f"Extracted {len(txt)} chars")
        q = st.text_area("Ask about the PDF")
        if st.button("Ask") and q:
            resp = ai_engine.generate_response(f"Document:\n{txt[:4000]}\n\nQ: {q}", "Answer in 1-2 sentences.")
            st.markdown(f"**AI:** {resp}")
            db.add_badge(st.session_state.user_id, "pdf_explorer")

def progress_tab():
    try:
        user = db.get_user(st.session_state.user_id) or {}
        c1,c2,c3 = st.columns(3)
        c1.metric("Queries", user.get("total_queries",0))
        c2.metric("Streak", f"{user.get('streak_days',0)} days")
        badges = json.loads(user.get("badges","[]"))
        c3.metric("Badges", len(badges))

        st.markdown('<span class="tab-header">### Your Badges</span>', unsafe_allow_html=True)
        for b in badges:
            st.markdown(f'<div class="badge-item">- {BADGES.get(b,b)}</div>', unsafe_allow_html=True)

        st.markdown('<span class="tab-header">### Leaderboards</span>', unsafe_allow_html=True)
        exam_lb = db.get_leaderboard("exam")
        essay_lb = db.get_leaderboard("essay")
        col1,col2 = st.columns(2)
        with col1:
            st.markdown('<div class="leaderboard"><b>Exam Prep</b></div>', unsafe_allow_html=True)
            if exam_lb:
                df = pd.DataFrame(exam_lb)
                st.dataframe(df, use_container_width=True)
                st.line_chart(df.set_index('email')['score'])
            else:
                st.info("No scores yet")
        with col2:
            st.markdown('<div class="leaderboard"><b>Essay Grader</b></div>', unsafe_allow_html=True)
            if essay_lb:
                df = pd.DataFrame(essay_lb)
                st.dataframe(df, use_container_width=True)
                st.line_chart(df.set_index('email')['score'])
            else:
                st.info("No scores yet")

        if date.today().day == 1:
            for uid, cat in db.get_monthly_leaders():
                db.apply_discount(uid, 0.10)
                st.success(f"10% discount applied to leader in **{cat}**!")
    except Exception as e:
        st.error("Progress tab error – see console.")
        print(e)

def exam_tab():
    st.markdown('<span class="tab-header">### Exam Prep</span>', unsafe_allow_html=True)
    exam = st.selectbox("Exam", list(EXAM_TYPES.keys()))
    subj = st.selectbox("Subject", EXAM_TYPES[exam]["subjects"])
    n = st.slider("Questions",1,10,5)
    if st.button("Generate"):
        with st.spinner("Generating…"):
            qs = ai_engine.generate_mcq_questions(subj, n)
        st.session_state.exam_questions = qs
        st.session_state.user_answers = {}
        st.rerun()

    if "exam_questions" in st.session_state:
        qs = st.session_state.exam_questions
        for i,q in enumerate(qs):
            st.markdown(f"**Q{i+1}:** {q['question']}")
            st.session_state.user_answers[i] = st.radio("Choose", q['options'], key=f"ans{i}")
        if st.button("Submit"):
            with st.spinner("Grading…"):
                res = ai_engine.grade_mcq(qs, st.session_state.user_answers)
                db.add_score(st.session_state.user_id, "exam", res["percentage"])
                if res["percentage"]==100:
                    db.add_badge(st.session_state.user_id, "perfect_score")
                    st.balloons()
                st.markdown(f"**Score: {res['percentage']}%** ({res['correct']}/{res['total']})")
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
            if res["score"]>=90:
                db.add_badge(st.session_state.user_id, "quiz_ace")
                st.balloons()
            st.markdown(f"**Score: {res['score']}/100** – {res['feedback']}")

def premium_tab():
    st.markdown('<div class="premium-header"><strong>Upgrade to Premium – KES 500/month</strong></div>', unsafe_allow_html=True)
    st.markdown("### Unlock Unlimited Access, Leaderboards, and More!")
    st.info("**Send KES 500 to M-Pesa Phone Number:**\n\n`0701617120`\n\n(Use your registered phone number)")
    st.markdown("---")
    phone = st.text_input("Your M-Pesa Phone Number (e.g. 07XXXXXXXX)")
    code = st.text_input("M-Pesa Transaction Code (e.g. RKA...)")
    if st.button("Submit Proof of Payment", type="primary"):
        if not phone or not code:
            st.error("Please fill both fields.")
        else:
            db.add_manual_payment(st.session_state.user_id, phone, code)
            st.success("Payment proof submitted! Admin will activate your Premium within 24 hrs.")
            st.balloons()

def settings_tab():
    st.markdown('<span class="tab-header">### Settings</span>', unsafe_allow_html=True)
    if db.is_2fa_enabled(st.session_state.user_id):
        st.success("2FA enabled")
        if st.button("Disable 2FA"):
            db.disable_2fa(st.session_state.user_id)
            st.rerun()
    else:
        st.info("Enable 2FA (Google Authenticator)")
        if st.button("Enable 2FA"):
            secret = db.generate_2fa_secret(st.session_state.user_id)
            st.image(qr_image(db.get_user(st.session_state.user_id)["email"], secret))
            st.code(secret)

    st.subheader("Appearance")
    theme = st.selectbox("Theme", ["light","dark"], index=0 if st.session_state.theme=="light" else 1)
    brightness = st.slider("Brightness",50,100,st.session_state.brightness)
    font = st.selectbox("Font",["sans-serif","serif","monospace"])
    pic = st.file_uploader("Profile picture",type=["jpg","png"])
    if st.button("Save Settings"):
        settings = {"theme":theme,"brightness":brightness,"font":font}
        if pic: settings["profile_pic"] = pic.read()
        db.update_settings(st.session_state.user_id, settings)
        for k,v in settings.items(): st.session_state[k]=v
        apply_theme()
        st.success("Saved!")

def parent_dashboard():
    st.markdown('<span class="tab-header">### Parent Dashboard</span>', unsafe_allow_html=True)
    kids = db.get_children(st.session_state.user_id)
    if not kids: st.info("No children linked."); return
    for k in kids:
        with st.expander(f"{k.get('name') or k['email']}"):
            st.write("Activity tracking coming soon…")

def admin_dashboard():
    if not st.session_state.is_admin: st.error("Access denied"); return
    st.markdown('<span class="tab-header">## Admin Dashboard</span>', unsafe_allow_html=True)
    users = db.get_all_users()
    if users:
        df = pd.DataFrame([dict(u) for u in users])
        if "created_at" in df.columns:
            df["created_at"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d")
        st.dataframe(df, use_container_width=True)

    st.subheader("User Management")
    uid = st.text_input("User ID")
    if uid:
        col1,col2,col3 = st.columns(3)
        with col1:
            if st.button("Add Premium"): db.toggle_premium(uid,True); st.success("Added")
        with col2:
            if st.button("Revoke Premium"): db.toggle_premium(uid,False); st.success("Revoked")
        with col3:
            if st.button("Revoke Badges"): db.revoke_user(uid); st.success("Done")

    st.markdown("### Pending Payments")
    pending = db.get_pending_manual_payments()
    if pending:
        for p in pending:
            p = dict(p)
            c1,c2,c3 = st.columns([4,1,1])
            with c1: st.write(f"**{p.get('name') or p.get('email')}** – `{p.get('mpesa_code')}`")
            with c2:
                if st.button("Approve",key=f"app{p['id']}"): db.approve_manual_payment(p["id"]); st.rerun()
            with c3:
                if st.button("Reject",key=f"rej{p['id']}"): db.reject_manual_payment(p["id"]); st.rerun()
    else:
        st.info("No pending requests")

# ────────────────────────────── MAIN ──────────────────────────────
def main():
    init_session()
    apply_theme()
    if st.session_state.show_welcome: welcome_screen(); return
    login_block()
    sidebar()

    # Build tabs — Premium only if NOT premium
    tabs = ["Chat Tutor","PDF Upload","Progress","Exam Prep","Essay Grader","Settings"]
    if not db.check_premium(st.session_state.user_id):
        tabs.insert(5, "Premium")
    if st.session_state.is_parent: tabs.append("Parent Dashboard")
    if st.session_state.is_admin: tabs.append("Admin Dashboard")

    tab_objs = st.tabs(tabs)

    # Fixed tab indexing
    idx = 0
    with tab_objs[idx]: chat_tab(); idx += 1
    with tab_objs[idx]: pdf_tab(); idx += 1
    with tab_objs[idx]: progress_tab(); idx += 1
    with tab_objs[idx]: exam_tab(); idx += 1
    with tab_objs[idx]: essay_tab(); idx += 1

    if "Premium" in tabs:
        with tab_objs[tabs.index("Premium")]: premium_tab(); idx += 1
    with tab_objs[idx]: settings_tab(); idx += 1

    if st.session_state.is_parent and "Parent Dashboard" in tabs:
        with tab_objs[tabs.index("Parent Dashboard")]: parent_dashboard()
    if st.session_state.is_admin and "Admin Dashboard" in tabs:
        with tab_objs[tabs.index("Admin Dashboard")]: admin_dashboard()

if __name__ == "__main__":
    main()
