# app.py
import streamlit as st
import pyotp
import qrcode
from io import BytesIO
import bcrypt
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, BADGES

st.set_page_config(page_title="LearnFlow AI", layout="wide")
st.markdown("<style>.main-header {font-size:2.5rem; text-align:center;}</style>", unsafe_allow_html=True)

@st.cache_resource
def init_db(): return Database()
@st.cache_resource
def init_ai(): 
    key = st.secrets.get("GEMINI_API_KEY", "")
    if not key: st.error("API Key missing!"); st.stop()
    return AIEngine(key)

db = init_db()
ai_engine = init_ai()

def init_session():
    defaults = {
        "logged_in": False, "user_id": None, "is_admin": False,
        "show_2fa_setup": False, "temp_2fa_secret": None,
        "chat_history": [], "current_subject": "Mathematics"
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

def generate_qr(email, secret):
    uri = pyotp.TOTP(secret).provisioning_uri(email, "LearnFlow AI")
    qr = qrcode.make(uri)
    buf = BytesIO()
    qr.save(buf, "PNG")
    return buf

def login_user(email, pwd, totp=""):
    user = db.get_user_by_email(email)
    if not user or not bcrypt.checkpw(pwd.encode(), user["password_hash"].encode()):
        return False, "Invalid credentials.", None
    if user.get("twofa_secret") and not pyotp.TOTP(user["twofa_secret"]).verify(totp):
        return False, "Invalid 2FA.", None
    db.update_user_activity(user["user_id"])
    return True, "Success!", user

def signup_user(email, pwd):
    if db.get_user_by_email(email): return False, "Email exists."
    if db.create_user(email, pwd): return True, "Created!"
    return False, "Failed."

def login_signup_block():
    if st.session_state.logged_in: return
    choice = st.radio("Action", ["Login", "Sign Up"], horizontal=True)
    email = st.text_input("Email", key=f"{choice.lower()}_email")
    pwd = st.text_input("Password", type="password", key=f"{choice.lower()}_pwd")
    totp = st.text_input("2FA Code (if enabled)", key="totp") if choice == "Login" else ""

    if st.button(choice):
        if choice == "Sign Up":
            success, msg = signup_user(email, pwd)
            st.write(msg)
            if success: st.success("Now log in.")
        else:
            success, msg, user = login_user(email, pwd, totp)
            st.write(msg)
            if success:
                st.session_state.update({
                    "logged_in": True, "user_id": user["user_id"],
                    "is_admin": user["role"] == "admin", "user": user
                })
                st.rerun()

    if st.session_state.logged_in and not st.session_state.show_2fa_setup:
        if not db.is_2fa_enabled(st.session_state.user_id):
            if st.button("Enable 2FA"):
                secret = pyotp.random_base32()
                db.enable_2fa(st.session_state.user_id, secret)
                st.session_state.temp_2fa_secret = secret
                st.session_state.show_2fa_setup = True
                st.rerun()

    if st.session_state.show_2fa_setup:
        st.markdown("### Scan QR Code")
        qr = generate_qr(st.session_state.user["email"], st.session_state.temp_2fa_secret)
        st.image(qr)
        code = st.text_input("Enter 6-digit code")
        if st.button("Verify"):
            if pyotp.TOTP(st.session_state.temp_2fa_secret).verify(code):
                st.success("2FA Enabled!")
                st.session_state.show_2fa_setup = False
                del st.session_state.temp_2fa_secret
                st.rerun()
            else:
                st.error("Invalid code.")

    st.stop()

def sidebar():
    with st.sidebar:
        st.markdown("## LearnFlow AI")
        if db.check_premium(st.session_state.user_id):
            st.success("PREMIUM")
        st.markdown(f"**Streak:** {db.update_streak(st.session_state.user_id)} days")
        st.session_state.current_subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))
        if st.button("Logout"):
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()

def main_chat():
    st.markdown(f"### {st.session_state.current_subject} Tutor")
    for msg in st.session_state.chat_history:
        st.markdown(f"**{'You' if msg['role']=='user' else 'AI'}:** {msg['content']}")
    q = st.text_area("Ask:", height=100)
    if st.button("Send") and q:
        st.session_state.chat_history.append({"role": "user", "content": q})
        with st.spinner("Thinking..."):
            resp = ai_engine.generate_response(q, get_enhanced_prompt(st.session_state.current_subject, q, ""))
        st.session_state.chat_history.append({"role": "assistant", "content": resp})
        db.add_chat_history(st.session_state.user_id, st.session_state.current_subject, q, resp)
        st.rerun()

def main():
    init_session()
    if not st.session_state.logged_in:
        st.markdown("### Welcome to LearnFlow AI")
        if st.button("Start"): st.rerun()
        login_signup_block()
    else:
        sidebar()
        tabs = st.tabs(["Chat", "Premium", "Admin"])
        with tabs[0]: main_chat()
        with tabs[1]:
            st.write("Pay KES 500 via M-Pesa")
            phone = st.text_input("Phone")
            code = st.text_input("M-Pesa Code")
            if st.button("Submit"): db.add_manual_payment(st.session_state.user_id, phone, code); st.success("Submitted!")
        if st.session_state.is_admin:
            with tabs.add_tab("Admin") if len(tabs) < 3 else tabs[2]:
                for p in db.get_pending_manual_payments():
                    st.write(f"{p['name']} - {p['mpesa_code']}")
                    if st.button("Approve", key=p["id"]): db.approve_manual_payment(p["id"]); st.rerun()

if __name__ == "__main__":
    main()
