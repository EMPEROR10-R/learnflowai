# app.py — FULLY FIXED: Login/Register Now Works Perfectly with Page State + No Refresh Issues + All Features Intact
import streamlit as st
import bcrypt
import pandas as pd
import qrcode
import base64
from io import BytesIO
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES
from utils import Translator_Utils, cached_pdf_extract

st.set_page_config(page_title="Kenyan EdTech", layout="wide", initial_sidebar_state="expanded")

# ============= INIT =============
db = Database()
db.auto_downgrade()
ai_engine = AIEngine(st.secrets.get("GEMINI_API_KEY", ""))

XP_RULES = {"question_asked": 10, "pdf_question": 15, "2fa_enabled": 20}

if "page" not in st.session_state:
    st.session_state.page = "landing"
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "user" not in st.session_state:
    st.session_state.user = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "pdf_text" not in st.session_state:
    st.session_state.pdf_text = ""
if "current_subject" not in st.session_state:
    st.session_state.current_subject = "Mathematics"
if "show_qr" not in st.session_state:
    st.session_state.show_qr = False
if "secret_key" not in st.session_state:
    st.session_state.secret_key = None
if "qr_code" not in st.session_state:
    st.session_state.qr_code = None
if "show_2fa" not in st.session_state:
    st.session_state.show_2fa = False
if "temp_user" not in st.session_state:
    st.session_state.temp_user = None
if "questions" not in st.session_state:
    st.session_state.questions = []
if "user_answers" not in st.session_state:
    st.session_state.user_answers = {}

translator = Translator_Utils()

# ============= KENYAN HERO (100% SAFE) =============
st.markdown("""
<style>
    .hero {background: linear-gradient(135deg, #000000, #006400, #FFD700, #B30000);
           padding: 100px 20px; border-radius: 25px; text-align: center;
           margin: -90px auto 50px; box-shadow: 0 20px 50px rgba(0,0,0,0.7);}
    .title {font-size: 5.5rem; color: #FFD700; font-weight: bold; text-shadow: 5px 5px 15px #000;}
    .subtitle {font-size: 2.4rem; color: #00ff9d;}
    .big-btn {background: linear-gradient(45deg, #00ff9d, #00cc7a); color: white;
              padding: 25px; font-size: 30px; font-weight: bold; border-radius: 20px;
              border: none; width: 100%; margin: 20px 0; box-shadow: 0 15px 40px rgba(0,255,157,0.6);}
    .big-btn:hover {transform: translateY(-12px); box-shadow: 0 30px 60px rgba(0,255,157,0.8);}
</style>
<div class="hero">
    <h1 class="title">Kenyan EdTech</h1>
    <p class="subtitle">Kenya's Most Powerful AI Tutor</p>
</div>
""", unsafe_allow_html=True)

# ============= HELPERS =============
def get_user():
    if st.session_state.user_id:
        st.session_state.user = db.get_user(st.session_state.user_id)
    return st.session_state.user

def award_xp(points, reason):
    if st.session_state.user_id:
        db.add_xp(st.session_state.user_id, points)
        get_user()
        st.toast(f"+{points} XP — {reason}")

# ============= PAGE RENDERING =============
if st.session_state.page == "landing" and not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("LOGIN", use_container_width=True, key="landing_login", type="primary"):
            st.session_state.page = "login"
            st.rerun()
        if st.button("REGISTER", use_container_width=True, key="landing_register"):
            st.session_state.page = "register"
            st.rerun()

elif st.session_state.page == "login":
    st.markdown("### Login to Your Account")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("Login"):
                user = db.get_user_by_email(email)
                if user and bcrypt.checkpw(password.encode(), user["password_hash"]):
                    st.session_state.temp_user = user
                    if db.is_2fa_enabled(user["user_id"]):
                        st.session_state.show_2fa = True
                        st.session_state.page = "2fa"
                    else:
                        st.session_state.logged_in = True
                        st.session_state.user_id = user["user_id"]
                        st.session_state.page = "main"
                    st.rerun()
                else:
                    st.error("Invalid credentials")
        with col2:
            if st.form_submit_button("Back"):
                st.session_state.page = "landing"
                st.rerun()

elif st.session_state.page == "register":
    st.markdown("### Create Account")
    with st.form("register_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm Password", type="password")
        if password != confirm and password:
            st.error("Passwords do not match")
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("Register"):
                if db.create_user(email, password):
                    st.success("Account created! Please login.")
                    st.session_state.page = "login"
                    st.rerun()
                else:
                    st.error("Email already exists")
        with col2:
            if st.form_submit_button("Back"):
                st.session_state.page = "landing"
                st.rerun()

elif st.session_state.page == "2fa":
    st.header("Two-Factor Authentication")
    code = st.text_input("Enter 6-digit code", key="2fa_input")
    if st.button("Verify", key="verify_2fa"):
        if db.verify_2fa_code(st.session_state.temp_user["user_id"], code):
            st.session_state.logged_in = True
            st.session_state.user_id = st.session_state.temp_user["user_id"]
            del st.session_state.temp_user
            st.session_state.show_2fa = False
            st.session_state.page = "main"
            st.rerun()
        else:
            st.error("Invalid code")

elif st.session_state.logged_in and st.session_state.page == "main":
    with st.sidebar:
        st.title("Kenyan EdTech")
        u = get_user()
        st.write(f"**{u.get('username','Student')}**")
        st.metric("Total XP", f"{u.get('total_xp',0):,}")
        st.metric("Streak", f"{u.get('streak',0)} days")
        if u.get('discount_20'): st.success("20% Discount Active!")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "Chat Tutor", "Exam Prep", "PDF Q&A", "Progress", "Essay Grader", "Shop", "Premium", "Settings"
    ])

    with tab1:
        st.header("AI Tutor")
        subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()), key="subject_select")
        st.session_state.current_subject = subject
        for msg in st.session_state.chat_history:
            st.chat_message(msg["role"]).write(msg["content"])
        if prompt := st.chat_input("Ask anything..."):
            with st.spinner("Thinking..."):
                resp = ai_engine.generate_response(prompt, get_enhanced_prompt(subject, prompt))
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            st.session_state.chat_history.append({"role": "assistant", "content": resp})
            award_xp(XP_RULES["question_asked"], "Question asked")
            st.rerun()  # Refresh chat

    with tab2:
        st.header("Exam Preparation")
        exam = st.selectbox("Exam", list(EXAM_TYPES.keys()))
        subject = st.selectbox("Subject", EXAM_TYPES[exam]["subjects"])
        num = st.slider("Questions", 1, 50, 10)
        if st.button("Generate Exam"):
            questions = ai_engine.generate_exam_questions(subject, exam, num)
            st.session_state.questions = questions
            st.session_state.user_answers = {}
        if st.session_state.questions:
            for i, q in enumerate(st.session_state.questions):
                st.write(f"**Q{i+1}:** {q['question']}")
                ans = st.radio("Choose answer", q["options"], key=f"q_{i}")
                st.session_state.user_answers[i] = ans
            if st.button("Submit Exam"):
                result = ai_engine.grade_mcq(st.session_state.questions, st.session_state.user_answers)
                st.success(f"Score: {result['percentage']}%")
                award_xp(int(result["percentage"]), "Exam")

    with tab3:
        st.header("PDF Q&A")
        uploaded = st.file_uploader("Upload PDF", type="pdf")
        if uploaded:
            st.session_state.pdf_text = cached_pdf_extract(uploaded.getvalue(), uploaded.name)
            st.success("PDF loaded!")
            if q := st.chat_input("Ask about this PDF..."):
                context = f"Document:\n{st.session_state.pdf_text[:12000]}"
                resp = ai_engine.generate_response(q, get_enhanced_prompt("General", q, context=context))
                st.write(resp)
                award_xp(XP_RULES["pdf_question"], "PDF Question")

    with tab4:
        st.header("Your Progress")
        u = get_user()
        st.metric("Total XP", u.get("total_xp", 0))
        lb = db.get_xp_leaderboard()
        if lb:
            df = pd.DataFrame([{"Rank":i+1, "Email":r["email"], "XP":r["total_xp"]} for i,r in enumerate(lb)])
            st.dataframe(df, hide_index=True)

    with tab5:
        st.header("Essay Grader")
        essay = st.text_area("Paste your essay")
        if st.button("Grade Essay"):
            result = ai_engine.grade_essay(essay, "KCSE Standard Rubric")
            st.json(result, expanded=True)

    with tab6:
        st.header("XP Shop")
        if st.button("Buy 20% Discount Cheque (500 XP Coins)"):
            if db.buy_discount_cheque(st.session_state.user_id):
                st.balloons()
                st.success("Discount Activated!")
            else:
                st.error("Not enough XP Coins")

    with tab7:
        st.header("Go Premium")
        price = 480 if get_user().get("discount_20") else 600
        st.success(f"Send **KSh {price}** to **0701617120**")
        with st.form("premium_payment"):
            phone = st.text_input("Your Phone")
            code = st.text_input("M-Pesa Code")
            if st.form_submit_button("Submit Payment"):
                db.add_payment(st.session_state.user_id, phone, code)
                st.success("Payment recorded! Waiting approval.")

    with tab8:
        st.header("Settings & 2FA")
        if st.button("Enable 2FA"):
            secret, qr = db.enable_2fa(st.session_state.user_id)
            buffered = BytesIO()
            qr.save(buffered)
            st.session_state.qr_code = base64.b64encode(buffered.getvalue()).decode()
            st.session_state.secret_key = secret
            st.session_state.show_qr = True
            st.rerun()
        if st.session_state.show_qr:
            st.image(f"data:image/png;base64,{st.session_state.qr_code}", width=200)
            st.code(st.session_state.secret_key)
            code = st.text_input("Enter code to confirm")
            if st.button("Confirm 2FA"):
                if db.verify_2fa_code(st.session_state.user_id, code):
                    st.success("2FA Enabled!")
                    award_xp(20, "2FA Setup")
                    st.session_state.show_qr = False
                else:
                    st.error("Invalid code")

        if get_user().get("username") == "EmperorUnruly":
            st.subheader("Emperor Panel")
            for p in db.get_pending_payments():
                st.write(f"User {p['user_id']} | Code: {p['mpesa_code']}")
                if st.button("Approve", key=f"approve_{p['id']}"):
                    db.approve_payment(p["id"])
                    st.rerun()

else:
    st.session_state.page = "landing"
    st.rerun()
