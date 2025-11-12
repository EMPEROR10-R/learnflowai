# app.py
import streamlit as st
import pyotp
import qrcode
from io import BytesIO
import bcrypt
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, BADGES

st.set_page_config(page_title="LearnFlow AI", layout="wide", page_icon="Kenya")
st.markdown("""
<style>
    @keyframes fadeInDown { from {opacity:0; transform:translateY(-30px);} to {opacity:1; transform:translateY(0);} }
    @keyframes pulse { 0%,100% {transform:scale(1);} 50% {transform:scale(1.05);} }
    .main-header {font-size:2.8rem; font-weight:bold;
        background:linear-gradient(135deg,#009E60,#FFD700,#CE1126);
        -webkit-background-clip:text; -webkit-text-fill-color:transparent;
        text-align:center; animation:fadeInDown 1s ease-out;}
    .welcome-box {background:linear-gradient(135deg,#009E60,#FFD700); padding:40px; border-radius:20px; color:white; text-align:center; animation:fadeInDown 1.2s;}
    .streak-badge {background:linear-gradient(135deg,#FF6B6B,#FFE66D); padding:8px 16px; border-radius:20px; color:white; font-weight:bold; animation:pulse 2s infinite;}
    .premium-badge {background:#FFD700; color:#000; padding:4px 12px; border-radius:12px; font-weight:bold;}
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
        "show_welcome": True, "show_2fa_setup": False, "temp_2fa_secret": None,
        "chat_history": [], "current_subject": "Mathematics"
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

def qr_code(email, secret):
    uri = pyotp.TOTP(secret).provisioning_uri(email, "LearnFlow AI")
    qr = qrcode.make(uri)
    buf = BytesIO()
    qr.save(buf, "PNG")
    return buf

def login_user(email, pwd, code=""):
    user = db.get_user_by_email(email)
    if not user or not bcrypt.checkpw(pwd.encode(), user["password_hash"].encode()):
        return False, "Invalid credentials.", None
    if user.get("twofa_secret") and not db.verify_2fa_code(user["user_id"], code):
        return False, "Invalid 2FA code.", None
    db.update_user_activity(user["user_id"])
    return True, "Success!", user

def signup_user(email, pwd):
    if db.get_user_by_email(email): return False, "Email exists."
    if db.create_user(email, pwd): return True, "Account created!"
    return False, "Failed."

def login_block():
    if st.session_state.logged_in: return
    st.markdown("### Login or Sign Up")
    choice = st.radio("Action", ["Login", "Sign Up"], horizontal=True)
    email = st.text_input("Email", key=f"{choice.lower()}_email")
    pwd = st.text_input("Password", type="password", key=f"{choice.lower()}_pwd")
    totp = st.text_input("2FA Code", key="totp") if choice == "Login" else ""

    if st.button(choice):
        if choice == "Sign Up":
            s, m = signup_user(email, pwd)
            st.write(m); st.success("Now log in.") if s else None
        else:
            s, m, u = login_user(email, pwd, totp)
            st.write(m)
            if s:
                st.session_state.update({
                    "logged_in": True, "user_id": u["user_id"],
                    "is_admin": u["role"] == "admin", "user": u
                })
                st.rerun()

    # 2FA Setup
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
        st.image(qr_code(st.session_state.user["email"], st.session_state.temp_2fa_secret))
        code = st.text_input("Enter code")
        if st.button("Verify"):
            if db.verify_2fa_code(st.session_state.user_id, code):
                st.success("2FA Enabled!")
                st.session_state.show_2fa_setup = False
                del st.session_state.temp_2fa_secret
                st.rerun()
            else:
                st.error("Invalid")

    st.stop()

def sidebar():
    with st.sidebar:
        st.markdown('<p class="main-header">LearnFlow AI</p>', unsafe_allow_html=True)
        if db.check_premium(st.session_state.user_id):
            st.markdown('<span class="premium-badge">PREMIUM</span>', unsafe_allow_html=True)
        streak = db.update_streak(st.session_state.user_id)
        st.markdown(f'<span class="streak-badge">Streak: {streak} days</span>', unsafe_allow_html=True)

        st.markdown("### Settings")
        st.session_state.current_subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))
        
        if st.button("Enable 2FA") if not db.is_2fa_enabled(st.session_state.user_id) else st.button("Disable 2FA"):
            if "Enable" in st.session_state.get("last_button", ""):  # toggle
                secret = pyotp.random_base32()
                db.enable_2fa(st.session_state.user_id, secret)
                st.session_state.temp_2fa_secret = secret
                st.session_state.show_2fa_setup = True
            else:
                db.disable_2fa(st.session_state.user_id)
            st.rerun()

        if st.button("Logout"):
            for k in list(st.session_state.keys()): del st.session_state[k]
            st.rerun()

def admin_center():
    st.subheader("Admin Control Center")
    tab1, tab2 = st.tabs(["Users", "Payments"])

    with tab1:
        users = db.get_all_users()
        for u in users:
            with st.expander(f"{u['name']} ({u['email']}) - {'Admin' if u['role']=='admin' else 'User'}"):
                if st.button("Delete", key=f"del_{u['user_id']}"):
                    if u["role"] != "admin":
                        db.delete_user(u["user_id"])
                        st.success("Deleted")
                        st.rerun()

    with tab2:
        payments = db.get_pending_manual_payments()
        for p in payments:
            with st.expander(f"{p['name']} - {p['phone']} - {p['mpesa_code']}"):
                if st.button("Approve", key=f"app_{p['id']}"):
                    db.approve_manual_payment(p["id"])
                    st.success("Approved!")
                    st.rerun()
                if st.button("Reject", key=f"rej_{p['id']}"):
                    db.reject_manual_payment(p["id"])
                    st.rerun()

def main_chat():
    st.markdown(f"### {st.session_state.current_subject} Tutor")
    for m in st.session_state.chat_history:
        st.markdown(f"**{'You' if m['role']=='user' else 'AI'}**: {m['content']}")
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

    # Welcome Animation
    if st.session_state.show_welcome:
        st.markdown("""
        <div class="welcome-box">
            <h1>LearnFlow AI</h1>
            <p>Your Kenyan AI Tutor</p>
            <p>KCPE • KPSEA • KJSEA • KCSE</p>
        </div>
        """, unsafe_allow_html=True)
        _, col, _ = st.columns([1,1,1])
        with col:
            if st.button("Start Learning!", type="primary", use_container_width=True):
                st.session_state.show_welcome = False
                st.rerun()
        return

    login_block()
    sidebar()

    tabs = st.tabs(["Chat", "Premium", "Admin Center"] if st.session_state.is_admin else ["Chat", "Premium"])
    with tabs[0]: main_chat()
    with tabs[1]:
        st.write("### Upgrade to Premium – KES 500/month")
        phone = st.text_input("M-Pesa Phone")
        code = st.text_input("Transaction Code")
        if st.button("Submit Proof"):
            db.add_manual_payment(st.session_state.user_id, phone, code)
            st.success("Submitted!")
    if st.session_state.is_admin:
        with tabs[2]: admin_center()

if __name__ == "__main__":
    main()
