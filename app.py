# app.py
import streamlit as st
import time
import bcrypt
import pyotp
import qrcode
from io import BytesIO
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS

st.set_page_config(page_title="LearnFlow AI", layout="wide")
st.markdown("<style>#MainMenu,footer,header{visibility:hidden;}</style>", unsafe_allow_html=True)

# INIT
@st.cache_resource
def get_db(): return Database()
@st.cache_resource
def get_ai():
    key = st.secrets.get("GEMINI_API_KEY", "")
    if not key: st.error("Add GEMINI_API_KEY"); st.stop()
    return AIEngine(key)

db = get_db()
ai = get_ai()

# WELCOME
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

# AUTH
def auth():
    st.markdown("<h1 style='text-align:center;color:#00d4b1;'>Welcome Back!</h1>", unsafe_allow_html=True)
    login, signup = st.tabs(["Login", "Sign Up"])

    with login:
        with st.form("login"):
            email = st.text_input("Email")
            pwd = st.text_input("Password", type="password")
            totp = st.text_input("2FA Code")
            if st.form_submit_button("Login"):
                ok, msg = login_user(email.lower(), pwd, totp)
                if ok:
                    st.success("Logged in!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(msg)

    with signup:
        with st.form("signup"):
            name = st.text_input("Name")
            email = st.text_input("Email")
            pwd = st.text_input("Password", type="password")
            phone = st.text_input("Phone")
            if st T.form_submit_button("Create Account"):
                if db.get_user_by_email(email.lower()):
                    st.error("Email exists")
                else:
                    db.create_user(name, email.lower(), pwd, phone)
                    st.success("Account created! Login now")
                    st.balloons()

# FIXED LOGIN (NO MORE SQLITE ERROR)
def login_user(email: str, password: str, totp_code: str = ""):
    user = db.get_user_by_email(email)
    if not user: return False, "User not found"

    stored = user["password_hash"]
    if isinstance(stored, str):
        stored = stored.encode('utf-8')
    if not bcrypt.checkpw(password.encode(), stored):
        return False, "Wrong password"

    if user.get("two_fa_secret"):
        if not totp_code or not pyotp.TOTP(user["two_fa_secret"]).verify(totp_code):
            return False, "Invalid 2FA"

    st.session_state.update({
        "logged_in": True,
        "user_id": user["user_id"],
        "user_name": user.get("name", "Student"),
        "user_email": email,
        "is_admin": user["role"] == "admin"
    })

    # FIXED: Safe activity log
    try:
        db.log_activity(user["user_id"], "login")
    except:
        pass  # ignore if table missing

    return True, ""

# FULL ADMIN PANEL
def admin_panel():
    st.title("ADMIN CONTROL CENTER")
    st.success("Welcome KingMumo!")

    tab1, tab2, tab3 = st.tabs(["Pending Payments", "All Users", "Revenue"])

    with tab1:
        payments = db.get_pending_payments()
        if not payments:
            st.info("No pending payments")
        else:
            for p in payments:
                with st.expander(f"{p['name']} - {p['phone']} - KSh 500"):
                    st.write(f"M-Pesa Code: `{p['mpesa_code']}`")
                    col1, col2 = st.columns(2)
                    if col1.button("APPROVE", key=p['id']):
                        db.approve_payment(p['id'])
                        st.success("Premium activated!")
                        st.rerun()
                    if col2.button("Reject", key=f"r{p['id']}"):
                        db.reject_payment(p['id'])
                        st.error("Rejected")
                        st.rerun()

    with tab2:
        users = db.get_all_users()
        df = st.dataframe([
            {"Name": u["name"], "Email": u["email"], "Role": u["role"], "Premium": "Yes" if u["is_premium"] else "No"}
            for u in users
        ], use_container_width=True)

    with tab3:
        total = db.get_revenue()
        st.metric("Total Revenue", f"KSh {total}")
        st.bar_chart(db.get_monthly_revenue())

# MAIN APP
def main_app():
    if st.session_state.is_admin:
        admin_panel()
    else:
        st.sidebar.success(f"Welcome {st.session_state.user_name}!")
        subject = st.sidebar.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))
        st.title(subject)
        if prompt := st.chat_input("Ask me anything..."):
            with st.chat_message("user"): st.write(prompt)
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    resp = ai.generate(f"{SUBJECT_PROMPTS[subject]}\nStudent: {prompt}")
                st.write(resp)

# ROUTER
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
