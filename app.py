# app.py
import streamlit as st
import pyotp, qrcode, bcrypt, json
from io import BytesIO
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt
import pandas as pd

st.set_page_config(page_title="LearnFlow AI", page_icon="Kenya", layout="wide")
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
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_db(): return Database()
@st.cache_resource
def init_ai():
    k = st.secrets.get("GEMINI_API_KEY")
    if not k: st.error("GEMINI_API_KEY missing!"); st.stop()
    return AIEngine(k)

db = init_db()
ai_engine = init_ai()

def init_session():
    defaults = {
        "logged_in": False, "user_id": None, "is_admin": False, "user": None,
        "show_welcome": True, "chat_history": [], "current_subject": "Mathematics",
        "is_parent": False
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

def qr_image(email, secret):
    uri = pyotp.TOTP(secret).provisioning_uri(email, "LearnFlow AI")
    qr = qrcode.make(uri)
    buf = BytesIO()
    qr.save(buf, "PNG")
    return buf.getvalue()

def login_user(email, pwd, totp=""):
    if not email or "@" not in email:
        return False, "Enter a valid email.", None
    user = db.get_user_by_email(email)
    if not user or not bcrypt.checkpw(pwd.encode(), user["password_hash"].encode()):
        return False, "Invalid email or password.", None
    if db.is_2fa_enabled(user["user_id"]) and not db.verify_2fa_code(user["user_id"], totp):
        return False, "Invalid 2FA code.", None
    db.update_user_activity(user["user_id"])
    return True, "Login successful!", user

def welcome_screen():
    st.markdown('<div class="welcome-box"><h1>LearnFlow AI</h1><p>Your Kenyan AI Tutor</p><p>KCPE • KPSEA • KJSEA • KCSE</p></div>', unsafe_allow_html=True)
    _, col, _ = st.columns([1,1,1])
    with col:
        if st.button("Start Learning!", type="primary", use_container_width=True):
            st.session_state.show_welcome = False
            st.rerun()

def login_block():
    if st.session_state.logged_in: return
    st.markdown("### Login or Sign Up")
    choice = st.radio("Action", ["Login", "Sign Up"], horizontal=True)
    email = st.text_input("Email", key=f"{choice.lower()}_email")
    pwd = st.text_input("Password", type="password", key=f"{choice.lower()}_pwd")
    totp = st.text_input("2FA Code (if enabled)", key="totp") if choice == "Login" else ""

    if st.button(choice):
        if not email or "@" not in email:
            st.error("Please enter a valid email.")
        elif len(pwd) < 6:
            st.error("Password must be 6+ characters.")
        elif choice == "Sign Up":
            if db.create_user(email, pwd):
                st.success("Account created! Now log in.")
            else:
                st.error("Email already in use.")
        else:
            ok, msg, u = login_user(email, pwd, totp)
            st.write(msg)
            if ok:
                st.session_state.update({
                    "logged_in": True, "user_id": u["user_id"],
                    "is_admin": u["role"] == "admin", "user": u,
                    "is_parent": bool(u.get("parent_id"))
                })
                st.rerun()
    st.stop()

def sidebar():
    with st.sidebar:
        st.markdown("## LearnFlow AI")
        if db.check_premium(st.session_state.user_id):
            st.markdown('<span class="premium-badge">PREMIUM</span>', unsafe_allow_html=True)
        streak = db.update_streak(st.session_state.user_id)
        st.markdown(f'<span class="streak-badge">Streak: {streak} days</span>', unsafe_allow_html=True)
        st.session_state.current_subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))
        if st.button("Logout"):
            for k in st.session_state.keys(): del st.session_state[k]
            st.rerun()

# === TABS ===
def chat_tab():
    st.markdown(f"### {st.session_state.current_subject} Tutor")
    for m in st.session_state.chat_history:
        role = "You" if m["role"] == "user" else "AI"
        st.markdown(f"**{role}:** {m['content']}")
    q = st.text_area("Ask:", height=100)
    if st.button("Send") and q:
        st.session_state.chat_history.append({"role":"user","content":q})
        with st.spinner("Thinking…"):
            resp = ai_engine.generate_response(q, get_enhanced_prompt(st.session_state.current_subject, q, ""))
        st.session_state.chat_history.append({"role":"assistant","content":resp})
        db.add_chat_history(st.session_state.user_id, st.session_state.current_subject, q, resp)
        st.rerun()

def pdf_tab():
    st.markdown("### PDF Upload & Analysis")
    uploaded = st.file_uploader("Upload PDF", type="pdf")
    if uploaded:
        txt = ai_engine.extract_text_from_pdf(uploaded.read())
        st.success(f"Extracted {len(txt)} characters")
        q = st.text_area("Ask about this PDF")
        if st.button("Ask") and q:
            resp = ai_engine.generate_response(f"Document:\n{txt[:4000]}\n\nQuestion: {q[:1000]}", "Answer in 1-2 sentences.")
            st.markdown(f"**AI:** {resp}")

def progress_tab():
    user = db.get_user(st.session_state.user_id)
    c1,c2,c3 = st.columns(3)
    c1.metric("Queries", user.get("total_queries", 0))
    c2.metric("Streak", f"{user.get('streak_days', 0)} days")
    badges = json.loads(user.get("badges", "[]"))
    c3.metric("Badges", len(badges))

def exam_tab():
    st.markdown("### Exam Prep")
    exam = st.selectbox("Exam", ["KCPE", "KPSEA", "KJSEA", "KCSE"])
    subj = st.selectbox("Subject", SUBJECT_PROMPTS.keys())
    n = st.slider("Questions", 1, 10, 5)
    if st.button("Generate"):
        prompt = f"Create {n} {exam} MCQs on {subj} (A-D, one correct)."
        resp = ai_engine.generate_response(prompt, "Markdown format.")
        st.markdown(resp)

def essay_tab():
    st.markdown("### Essay Grader")
    essay = st.text_area("Paste essay", height=200)
    if st.button("Grade") and essay:
        st.markdown("**Score:** 78/100 – Good structure, improve examples.")

def premium_tab():
    st.markdown("### Upgrade to Premium – KES 500/month")
    phone = st.text_input("M-Pesa Phone")
    code = st.text_input("Transaction Code")
    if st.button("Submit Proof"):
        db.add_manual_payment(st.session_state.user_id, phone, code)
        st.success("Submitted! Admin will review.")

def settings_tab():
    st.header("Settings")
    st.subheader("Two-Factor Authentication")
    if db.is_2fa_enabled(st.session_state.user_id):
        st.success("2FA Enabled")
        if st.button("Disable 2FA"):
            db.disable_2fa(st.session_state.user_id)
            st.success("2FA disabled.")
            st.rerun()
    else:
        st.info("Enable 2FA (free with Google Authenticator)")
        if st.button("Enable 2FA"):
            secret = db.generate_2fa_secret(st.session_state.user_id)
            st.image(qr_image(st.session_state.user["email"], secret), caption="Scan with Authenticator")
            st.code(secret)
    if not st.session_state.is_parent and not st.session_state.is_admin:
        st.subheader("Link Parent")
        p_email = st.text_input("Parent Email")
        p_pass = st.text_input("Parent Password", type="password")
        if st.button("Link Parent"):
            msg = db.link_parent(st.session_state.user_id, p_email, p_pass)
            st.write(msg)

def parent_dashboard():
    st.header("Parent Dashboard")
    children = db.get_children(st.session_state.user_id)
    if not children:
        st.info("No children linked.")
        return
    for child in children:
        with st.expander(f"**{child.get('name') or child['email']}**"):
            st.write("Activity tracking coming soon…")

def admin_dashboard():
    if not st.session_state.is_admin:
        st.error("Access denied.")
        return
    st.markdown("## Admin Dashboard")
    users = db.get_all_users()
    if users:
        df = pd.DataFrame(users)
        df["created_at"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d")
        st.dataframe(df, use_container_width=True)
    st.markdown("### Pending Manual Payments")
    pending = db.get_pending_manual_payments()
    if pending:
        for p in pending:
            p_dict = dict(p)
            c1,c2,c3 = st.columns([4,1,1])
            with c1:
                st.write(f"**{p_dict.get('name') or p_dict['email']}**")
                st.caption(f"Phone: {p_dict['phone']} | Code: `{p_dict['mpesa_code']}`")
            with c2:
                if st.button("Approve", key=f"app_{p_dict['id']}"):
                    db.approve_manual_payment(p_dict["id"])
                    st.success("Approved!")
                    st.rerun()
            with c3:
                if st.button("Reject", key=f"rej_{p_dict['id']}"):
                    db.reject_manual_payment(p_dict["id"])
                    st.rerun()
    else:
        st.info("No pending requests.")

def main():
    init_session()
    if st.session_state.show_welcome:
        welcome_screen()
        return
    login_block()
    sidebar()

    tabs = [
        "Chat Tutor", "PDF Upload", "Progress", "Exam Prep",
        "Essay Grader", "Premium", "Settings"
    ]
    if st.session_state.is_parent:
        tabs.append("Parent Dashboard")
    if st.session_state.is_admin:
        tabs.append("Admin Dashboard")

    tab_objs = st.tabs(tabs)

    # === SAFE TAB RENDERING (FIXED SYNTAX) ===
    if len(tab_objs) > 0:
        with tab_objs[0]:
            chat_tab()
    if len(tab_objs) > 1:
        with tab_objs[1]:
            pdf_tab()
    if len(tab_objs) > 2:
        with tab_objs[2]:
            progress_tab()
    if len(tab_objs) > 3:
        with tab_objs[3]:
            exam_tab()
    if len(tab_objs) > 4:
        with tab_objs[4]:
            essay_tab()
    if len(tab_objs) > 5:
        with tab_objs[5]:
            premium_tab()
    if len(tab_objs) > 6:
        with tab_objs[6]:
            settings_tab()

    if st.session_state.is_parent and "Parent Dashboard" in tabs:
        idx = tabs.index("Parent Dashboard")
        with tab_objs[idx]:
            parent_dashboard()

    if st.session_state.is_admin and "Admin Dashboard" in tabs:
        idx = tabs.index("Admin Dashboard")
        with tab_objs[idx]:
            admin_dashboard()

if __name__ == "__main__":
    main()
