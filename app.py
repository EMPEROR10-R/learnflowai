# app.py — FULLY COMPLETE, 100% RESTORED, NO CRASH (November 2025)
import streamlit as st
import bcrypt
import pandas as pd
import qrcode
import base64
import io
import PyPDF2
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES
from utils import VoiceInputHelper, Translator_Utils, cached_pdf_extract

# ============= CONFIG =============
st.set_page_config(page_title="Kenyan EdTech", layout="wide", initial_sidebar_state="expanded")

# ============= INIT =============
db = Database()
db.auto_downgrade()
ai_engine = AIEngine(st.secrets.get("GEMINI_API_KEY", ""))

XP_RULES = {"question_asked": 10, "pdf_question": 15, "quiz_generated": 5, "2fa_enabled": 20}

if "initialized" not in st.session_state:
    st.session_state.update({
        "logged_in": False, "user_id": None, "user": None,
        "chat_history": [], "pdf_text": "", "current_subject": "Mathematics",
        "show_qr": False, "secret_key": None, "qr_code": None,
        "show_2fa": False, "temp_user": None,
        "questions": [], "user_answers": {},
        "login": False, "register": False
    })

translator = Translator_Utils()

# ============= 100% SAFE KENYAN HERO (NO IMAGE DOWNLOAD) =============
st.markdown("""
<style>
    .hero {
        background: linear-gradient(135deg, #000000, #006400, #FFD700, #B30000);
        padding: 90px 20px;
        border-radius: 20px;
        text-align: center;
        margin: -80px auto 40px;
        box-shadow: 0 15px 40px rgba(0,0,0,0.6);
    }
    .title { font-size: 5rem; color: #FFD700; font-weight: bold; text-shadow: 4px 4px 12px #000; margin: 0; }
    .subtitle { font-size: 2.2rem; color: #00ff9d; margin: 15px 0 0; }
    .big-btn {
        background: linear-gradient(45deg, #00ff9d, #00cc7a);
        color: white; padding: 22px; font-size: 28px; font-weight: bold;
        border-radius: 18px; border: none; width: 100%; margin: 18px 0;
        box-shadow: 0 12px 35px rgba(0,255,157,0.5);
        transition: all 0.4s;
    }
    .big-btn:hover { transform: translateY(-10px); box-shadow: 0 25px 50px rgba(0,255,157,0.7); }
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

def safe_add_chat(subject, user_msg, ai_msg):
    try: db.add_chat_history(st.session_state.user_id, subject, user_msg, ai_msg)
    except: pass

# ============= LANDING PAGE =============
def landing_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("LOGIN", use_container_width=True, key="login"):
            st.session_state.login = True; st.rerun()
        if st.button("REGISTER", use_container_width=True, key="reg"):
            st.session_state.register = True; st.rerun()

    if st.session_state.login or st.session_state.register:
        st.markdown(f"### {'Login' if st.session_state.login else 'Register'}")
        with st.form("auth"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Submit"):
                if st.session_state.login:
                    user = db.get_user_by_email(email)
                    if user and bcrypt.checkpw(password.encode(), user["password_hash"]):
                        st.session_state.temp_user = user
                        st.session_state.show_2fa = db.is_2fa_enabled(user["user_id"])
                        if not st.session_state.show_2fa:
                            st.session_state.logged_in = True
                            st.session_state.user_id = user["user_id"]
                            st.rerun()
                    else:
                        st.error("Wrong email or password")
                else:
                    if db.create_user(email, password):
                        st.success("Account created! Login now.")
                        st.session_state.login = True
                        st.session_state.register = False
                        st.rerun()
                    else:
                        st.error("Email taken")

# ============= 2FA =============
if st.session_state.get("show_2fa"):
    st.header("Two-Factor Authentication")
    code = st.text_input("Enter 6-digit code")
    if st.button("Verify"):
        if db.verify_2fa_code(st.session_state.temp_user["user_id"], code):
            st.session_state.logged_in = True
            st.session_state.user_id = st.session_state.temp_user["user_id"]
            del st.session_state.temp_user
            del st.session_state.show_2fa
            st.rerun()
        else:
            st.error("Invalid code")

# ============= MAIN APP (FULLY RESTORED) =============
elif st.session_state.logged_in:
    with st.sidebar:
        st.title("Kenyan EdTech")
        u = get_user()
        st.write(f"**{u.get('username','Student')}**")
        st.metric("Total XP", f"{u.get('total_xp',0):,}")
        st.metric("Spendable XP", f"{u.get('spendable_xp',0):,}")
        st.metric("XP Coins", f"{u.get('xp_coins',0):,}")
        st.metric("Streak", f"{u.get('streak',0)} days")
        if u.get('discount_20'): st.success("20% Discount Active!")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "Chat Tutor", "Exam Prep", "PDF Q&A", "Progress", "Essay Grader", "Shop", "Premium", "Settings"
    ])

    with tab1:
        st.header("AI Tutor")
        subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))
        st.session_state.current_subject = subject
        for msg in st.session_state.chat_history:
            st.chat_message(msg["role"]).write(msg["content"])
        if prompt := st.chat_input("Ask anything..."):
            with st.spinner("Thinking..."):
                resp = ai_engine.generate_response(prompt, get_enhanced_prompt(subject, prompt))
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            st.session_state.chat_history.append({"role": "assistant", "content": resp})
            safe_add_chat(subject, prompt, resp)
            award_xp(XP_RULES["question_asked"], "Question")

    with tab2:
        st.header("Exam Preparation")
        exam = st.selectbox("Exam", list(EXAM_TYPES.keys()))
        subject = st.selectbox("Subject", EXAM_TYPES[exam]["subjects"])
        num = st.slider("Questions", 1, 100, 10)
        if st.button("Generate"):
            questions = ai_engine.generate_exam_questions(subject, exam, num)
            st.session_state.questions = questions
            st.session_state.user_answers = {}
        if st.session_state.questions:
            for i, q in enumerate(st.session_state.questions):
                st.write(f"**Q{i+1}:** {q['question']}")
                st.session_state.user_answers[i] = st.radio("", q["options"], key=f"a{i}")
            if st.button("Submit Exam"):
                result = ai_engine.grade_mcq(st.session_state.questions, st.session_state.user_answers)
                st.success(f"Score: {result['percentage']}%")
                db.add_score(st.session_state.user_id, "exam", result["percentage"])
                award_xp(int(result["percentage"]), "Exam")

    with tab3:
        st.header("PDF Q&A")
        uploaded = st.file_uploader("Upload PDF", type="pdf")
        if uploaded:
            st.session_state.pdf_text = cached_pdf_extract(uploaded.getvalue(), uploaded.name)
            st.success("PDF loaded")
            if q := st.chat_input("Ask about this PDF"):
                context = f"Document:\n{st.session_state.pdf_text[:12000]}"
                resp = ai_engine.generate_response(q, get_enhanced_prompt("General", q, context=context))
                st.write(resp)
                award_xp(XP_RULES["pdf_question"], "PDF Q")

    with tab4:
        st.header("Progress")
        u = get_user()
        st.metric("Total XP", u.get("total_xp", 0))
        lb = db.get_xp_leaderboard()
        if lb: st.dataframe(pd.DataFrame([{"Rank":i+1,"Email":r["email"],"XP":r["total_xp"]} for i,r in enumerate(lb)]))

    with tab5:
        st.header("Essay Grader")
        essay = st.text_area("Paste essay")
        if st.button("Grade"):
            result = ai_engine.grade_essay(essay, "KCSE Standard")
            st.json(result)

    with tab6:
        st.header("XP Shop")
        if st.button("Buy 20% Discount (500 XP Coins)"):
            if db.buy_discount_cheque(st.session_state.user_id):
                st.balloons()
            else:
                st.error("Not enough coins")

    with tab7:
        st.header("Go Premium")
        price = 480 if get_user().get("discount_20") else 600
        st.write(f"Send **KSh {price}** to **0701617120**")
        with st.form("pay"):
            phone = st.text_input("Phone")
            code = st.text_input("M-Pesa Code")
            if st.form_submit_button("Submit"):
                db.add_payment(st.session_state.user_id, phone, code)
                st.success("Submitted!")

    with tab8:
        st.header("Settings")
        if get_user().get("username") == "EmperorUnruly":
            st.subheader("Emperor Panel")
            for p in db.get_pending_payments():
                st.write(p)
                if st.button("Approve", key=p["id"]):
                    db.approve_payment(p["id"])
                    st.rerun()

else:
    landing_page()
