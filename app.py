# app.py
import streamlit as st
import time
import bcrypt
import pyotp
import qrcode
import pandas as pd
from io import BytesIO
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, BADGES

# =============================================
# 1. PAGE CONFIG & HIDE BRANDING
# =============================================
st.set_page_config(page_title="LearnFlow AI", layout="wide", menu_items=None)
st.markdown("""
<style>
    #MainMenu, header, footer {visibility: hidden !important;}
    .stApp > div:last-child {display: none !important;}
    .block-container {padding-top: 2rem;}
</style>
""", unsafe_allow_html=True)

# =============================================
# 2. SAFE INIT (NO CRASH)
# =============================================
def init_app():
    try:
        db = Database()
    except Exception as e:
        st.error("Database failed. Run `python fix_db.py` locally.")
        st.code(f"Error: {e}")
        st.stop()

    key = st.secrets.get("GEMINI_API_KEY", "")
    if not key:
        st.error("GEMINI_API_KEY missing!")
        st.info("Add in Streamlit Cloud → Settings → Secrets")
        st.stop()

    try:
        ai = AIEngine(key)
    except Exception as e:
        st.error("AI Engine failed.")
        st.code(f"Error: {e}")
        st.stop()

    return db, ai

db, ai = init_app()

# =============================================
# 3. APPLY SETTINGS
# =============================================
def apply_settings():
    font = st.session_state.get("font_size", 16)
    theme = st.session_state.get("theme", "light")
    st.markdown(f"""
    <style>
    .stApp {{font-size:{font}px;}}
    .stApp {{background:{'#fff' if theme=='light' else '#1e1e1e'};color:{'#000' if theme=='light' else '#fff'};}}
    </style>
    """, unsafe_allow_html=True)

# =============================================
# 4. WELCOME PAGE
# =============================================
def welcome():
    st.markdown("""
    <div style='text-align:center;padding:100px;'>
        <h1 style='font-size:70px;background:-webkit-linear-gradient(#00d4b1,#00ffaa);
                   -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                   animation:glow 2s infinite alternate;'>
            LearnFlow AI
        </h1>
        <p style='font-size:24px;color:#aaa;'>Kenya's #1 AI Tutor</p>
        <br><br>
        <button onclick="document.getElementById('go').click()"
                style='padding:16px 60px;font-size:22px;background:#00d4b1;color:black;
                       border:none;border-radius:50px;cursor:pointer;'>
            Continue
        </button>
    </div>
    <style>@keyframes glow{from{text-shadow:0 0 20px #00d4b1}to{text-shadow:0 0 40px #00ffcc}}</style>
    """, unsafe_allow_html=True)
    if st.button("Continue", key="go", use_container_width=True):
        st.session_state.page = "auth"
        st.rerun()

# =============================================
# 5. AUTH PAGE
# =============================================
def auth():
    st.markdown("<h1 style='text-align:center;color:#00d4b1;'>Welcome Back!</h1>", unsafe_allow_html=True)
    login_tab, signup_tab = st.tabs(["Login", "Sign Up"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email")
            pwd = st.text_input("Password", type="password")
            totp = st.text_input("2FA Code (if enabled)")
            if st.form_submit_button("Login"):
                ok, msg = login_user(email.lower(), pwd, totp)
                if ok:
                    st.success("Logged in!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(msg)

    with signup_tab:
        with st.form("signup_form"):
            name = st.text_input("Name")
            email = st.text_input("Email")
            pwd = st.text_input("Password", type="password")
            phone = st.text_input("Phone")
            if st.form_submit_button("Create Account"):
                if db.get_user_by_email(email.lower()):
                    st.error("Email exists")
                else:
                    db.create_user(name, email.lower(), pwd, phone)
                    st.success("Account created! Login now.")
                    st.balloons()

# =============================================
# 6. LOGIN LOGIC
# =============================================
def login_user(email: str, password: str, totp_code: str = ""):
    user = db.get_user_by_email(email)
    if not user:
        return False, "User not found"

    stored = user["password_hash"]
    if isinstance(stored, str):
        stored = stored.encode()
    if not bcrypt.checkpw(password.encode(), stored):
        return False, "Wrong password"

    if user.get("two_fa_secret"):
        if not totp_code or not pyotp.TOTP(user["two_fa_secret"]).verify(totp_code):
            return False, "Invalid 2FA code"

    st.session_state.update({
        "logged_in": True,
        "user_id": user["user_id"],
        "user_name": user.get("name", "Student"),
        "user_email": email,
        "is_admin": user["role"] == "admin",
        "is_premium": bool(user["is_premium"]),
    })
    return True, ""

# =============================================
# 7. ADMIN CENTER
# =============================================
def admin_control_center():
    st.title("ADMIN CONTROL CENTER")
    st.success("Welcome KingMumo!")

    t1, t2, t3 = st.tabs(["Pending Payments", "Users", "Revenue"])

    with t1:
        payments = db.get_pending_payments()
        if not payments:
            st.info("No pending payments")
        else:
            for p in payments:
                with st.expander(f"{p['name']} – {p['phone']} – KSh 500"):
                    st.write(f"**Ref:** `{p['mpesa_code']}`")
                    st.write(f"**Phone:** {p['phone']}")
                    c1, c2 = st.columns(2)
                    if c1.button("APPROVE", key=f"a{p['id']}"):
                        db.approve_payment(p["id"])
                        st.success("Approved!"); st.rerun()
                    if c2.button("Reject", key=f"r{p['id']}"):
                        db.reject_payment(p["id"]); st.rerun()

    with t2:
        users = db.get_all_users()
        st.dataframe([{"Name": u["name"], "Email": u["email"], "Premium": "Yes" if u["is_premium"] else "No"} for u in users], use_container_width=True)

    with t3:
        st.metric("Revenue", f"KSh {db.get_revenue()}")

# =============================================
# 8. SETTINGS (2FA for ALL)
# =============================================
def settings_page():
    st.title("Settings")
    with st.form("settings_form"):
        st.session_state.font_size = st.slider("Font Size", 12, 24, st.session_state.get("font_size", 16))
        st.session_state.theme = st.selectbox("Theme", ["light", "dark"], index=0 if st.session_state.get("theme", "light")=="light" else 1)

        user = db.get_user_by_email(st.session_state.user_email)
        has_2fa = bool(user.get("two_fa_secret"))
        enable_2fa = st.checkbox("Enable 2FA", value=has_2fa)

        qr_img = None
        if enable_2fa and not has_2fa:
            secret = pyotp.random_base32()
            uri = pyotp.totp.TOTP(secret).provisioning_uri(name=st.session_state.user_email, issuer_name="LearnFlow AI")
            qr = qrcode.make(uri)
            buf = BytesIO(); qr.save(buf, format="PNG"); qr_img = buf.getvalue()
            st.session_state._temp_2fa = secret

        if qr_img:
            st.image(qr_img, caption="Scan with Authenticator")
            st.info("Save to activate.")

        if st.form_submit_button("Save"):
            if enable_2fa and not has_2fa:
                db.enable_2fa(st.session_state.user_id, st.session_state._temp_2fa)
                del st.session_state._temp_2fa
            elif not enable_2fa and has_2fa:
                db.disable_2fa(st.session_state.user_id)
            st.success("Saved!"); time.sleep(1); st.rerun()

# =============================================
# 9. MAIN APP – Dashboard (Admin = Unlimited)
# =============================================
def main_app():
    apply_settings()

    # Sidebar
    st.sidebar.success(f"Welcome {st.session_state.user_name}!")

    if st.sidebar.button("Dashboard"):
        st.session_state.page = "dashboard"
    if st.sidebar.button("Settings"):
        st.session_state.page = "settings"
    if st.sidebar.button("Logout"):
        # SAFE LOGOUT
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.session_state.page = "auth"
        st.rerun()

    if st.session_state.is_admin:
        if st.sidebar.button("Admin Centre"):
            st.session_state.page = "admin_center"

    # Routing
    if st.session_state.get("page") == "admin_center":
        admin_control_center(); return
    if st.session_state.get("page") == "settings":
        settings_page(); return

    # DASHBOARD
    st.title("Dashboard")
    if st.session_state.is_admin:
        st.success("**Unlimited Access**")
    elif st.session_state.is_premium:
        st.info("Premium User")
    else:
        st.warning("Upgrade to Premium!")

    subject = st.sidebar.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))
    mode = st.sidebar.radio("Mode", ["Chat", "Quiz"], horizontal=True)
    if mode == "Quiz":
        show_quiz_mode(subject)
    else:
        show_chat_mode(subject)

# =============================================
# 10. QUIZ & CHAT
# =============================================
def show_quiz_mode(subject):
    if st.button("Start Quiz"):
        qs = ai.generate_mcq_questions(subject, 5)
        st.session_state.quiz = {"questions": qs, "answers": {}, "start": time.time()}
        st.rerun()
    if "quiz" in st.session_state:
        q = st.session_state.quiz
        for i, ques in enumerate(q["questions"]):
            with st.expander(f"Q{i+1}: {ques['question']}"):
                ans = st.radio("Choose", ques["options"], key=f"q{i}")
                q["answers"][i] = ans
        if st.button("Submit"):
            res = ai.grade_mcq(q["questions"], q["answers"])
            db.record_quiz_score(st.session_state.user_id, subject, res["correct"], res["total"])
            st.success(f"Score: {res['correct']}/{res['total']}")
            del st.session_state.quiz
            st.rerun()

def show_chat_mode(subject):
    prompt = st.chat_input("Ask...")
    if prompt:
        with st.chat_message("user"): st.write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                resp = ai.generate_response(f"{SUBJECT_PROMPTS[subject]}\nStudent: {prompt}", SUBJECT_PROMPTS[subject])
            st.write(resp)

# =============================================
# 11. ROUTER
# =============================================
if "page" not in st.session_state:
    st.session_state.page = "welcome"

if st.session_state.page == "welcome":
    welcome()
elif st.session_state.page == "auth":
    auth()
elif st.session_state.get("logged_in"):
    main_app()
else:
    st.session_state.page = "auth"
    st.rerun()
