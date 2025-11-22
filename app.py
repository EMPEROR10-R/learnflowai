# app.py — UPDATED 2025: Added Inventory Tracking Table + Exponential Prices for All Items + Admin Full Controls + Tables/Graphs + All Features Intact & Working
import streamlit as st
import bcrypt
import pandas as pd
import qrcode
import base64
from io import BytesIO
import matplotlib.pyplot as plt
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
        st.toast(f"+{points} XP & Coins — {reason}")

def calculate_level_progress(total_xp):
    if total_xp == 0:
        return 1, 0.0, 0, 100
    level = 1
    xp_needed = 100
    current_xp = total_xp
    while current_xp >= xp_needed:
        current_xp -= xp_needed
        level += 1
        xp_needed = int(xp_needed * 1.5)  # Exponential increase
    progress = current_xp / xp_needed
    return level, progress, current_xp, xp_needed

def calculate_item_price(base_price, buy_count):
    return int(base_price * (2 ** buy_count))  # Exponential increase

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
        level, progress, current_xp, xp_needed = calculate_level_progress(u.get('total_xp', 0))
        st.metric("Level", level)
        st.progress(progress)
        st.caption(f"{current_xp} / {xp_needed} XP to Level {level + 1}")
        st.metric("Total XP", f"{u.get('total_xp',0):,}")
        st.metric("XP Coins", f"{u.get('xp_coins',0):,}")
        st.metric("Streak", f"{u.get('streak',0)} days")
        if u.get('discount_20'): st.success("20% Discount Active!")

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "Chat Tutor", "Exam Prep", "PDF Q&A", "Progress", "Essay Grader", "XP Shop", "Premium", "Settings"
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
        topics = EXAM_TYPES[exam]["topics"].get(subject, ["General"])
        topic = st.selectbox("Topic", topics)
        num = st.slider("Questions", 1, 50, 10)
        if st.button("Generate Exam"):
            questions = ai_engine.generate_exam_questions(subject, exam, num, topic)
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
                db.add_score(st.session_state.user_id, f'exam_{subject}', result['percentage'])
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
        st.header("Your Progress & Leaderboards")
        u = get_user()
        st.metric("Total XP", u.get("total_xp", 0))
        st.subheader("Global Level Leaderboard")
        lb = db.get_xp_leaderboard()
        if lb:
            df = pd.DataFrame([{"Rank":i+1, "Email":r["email"], "XP":r["total_xp"], "Level": calculate_level_progress(r["total_xp"])[0]} for i,r in enumerate(lb)])
            st.dataframe(df, hide_index=True)
            # Graph
            fig, ax = plt.subplots()
            ax.bar(df["Email"], df["Level"])
            ax.set_ylabel("Level")
            ax.set_title("Global Levels Graph")
            st.pyplot(fig)
        st.subheader("Subject Exam Leaderboards")
        selected_subject = st.selectbox("Select Subject for Leaderboard", list(SUBJECT_PROMPTS.keys()))
        subject_lb = db.get_leaderboard(f'exam_{selected_subject}')
        if subject_lb:
            df_subject = pd.DataFrame([{"Rank":i+1, "Email":r["email"], "Avg Score":r["score"]} for i,r in enumerate(subject_lb)])
            st.dataframe(df_subject, hide_index=True)
            # Graph
            fig2, ax2 = plt.subplots()
            ax2.bar(df_subject["Email"], df_subject["Avg Score"])
            ax2.set_ylabel("Avg Score")
            ax2.set_title(f"{selected_subject} Scores Graph")
            st.pyplot(fig2)
        st.subheader("Essay Grader Leaderboard")
        essay_lb = db.get_leaderboard('essay')
        if essay_lb:
            df_essay = pd.DataFrame([{"Rank":i+1, "Email":r["email"], "Avg Score":r["score"]} for i,r in enumerate(essay_lb)])
            st.dataframe(df_essay, hide_index=True)
            # Graph
            fig3, ax3 = plt.subplots()
            ax3.bar(df_essay["Email"], df_essay["Avg Score"])
            ax3.set_ylabel("Avg Score")
            ax3.set_title("Essay Scores Graph")
            st.pyplot(fig3)

    with tab5:
        st.header("Essay Grader")
        essay = st.text_area("Paste your essay")
        if st.button("Grade Essay"):
            result = ai_engine.grade_essay(essay, "KCSE Standard Rubric")
            st.json(result, expanded=True)
            db.add_score(st.session_state.user_id, 'essay', result['score'])

    with tab6:
        st.header("XP Shop")
        st.metric("Your XP Coins", u.get('xp_coins', 0))
        # Discount Cheque
        discount_buy_count = u.get('discount_buy_count', 0)
        discount_price = calculate_item_price(5000000, discount_buy_count)
        st.write(f"20% Discount Cheque ({discount_price:,} XP Coins)")
        if st.button("Buy Discount Cheque"):
            if db.buy_discount_cheque(st.session_state.user_id):
                st.balloons()
                st.success("Discount Activated!")
            else:
                st.error("Not enough XP Coins")
        # Extra Daily Questions
        extra_questions_count = u.get('extra_questions_buy_count', 0)
        extra_questions_price = calculate_item_price(100, max(0, extra_questions_count - 1)) if extra_questions_count > 1 else 100
        st.write(f"Extra Daily Questions (+10) ({extra_questions_price:,} XP Coins)")
        if st.button("Buy Extra Questions"):
            if db.buy_extra_questions(st.session_state.user_id):
                st.success("Extra Questions Added!")
            else:
                st.error("Not enough XP Coins")
        # Custom Badge
        custom_badge_count = u.get('custom_badge_buy_count', 0)
        custom_badge_price = calculate_item_price(500000, max(0, custom_badge_count - 1)) if custom_badge_count > 1 else 500000
        st.write(f"Custom Badge ({custom_badge_price:,} XP Coins)")
        if st.button("Buy Custom Badge"):
            if db.buy_custom_badge(st.session_state.user_id):
                st.success("Custom Badge Unlocked!")
            else:
                st.error("Not enough XP Coins")

        # NEW: Inventory Tracking Table
        st.subheader("Your Inventory")
        purchases = db.get_user_purchases(st.session_state.user_id)
        if purchases:
            df_purchases = pd.DataFrame(purchases)
            st.dataframe(df_purchases, hide_index=True)
        else:
            st.info("No purchases yet.")

    with tab7:
        st.header("Go Premium")
        if u.get('username') == "EmperorUnruly":
            st.success("Admin Account: Full-Time Premium Access")
        elif u.get('is_premium', 0) == 0:
            price = 480 if u.get("discount_20") else 600
            st.success(f"Send **KSh {price}** to **0701617120**")
            with st.form("premium_payment"):
                phone = st.text_input("Your Phone")
                code = st.text_input("M-Pesa Code")
                if st.form_submit_button("Submit Payment"):
                    db.add_payment(st.session_state.user_id, phone, code)
                    st.success("Payment recorded! Waiting approval.")
        else:
            st.success("You are already Premium!")

    with tab8:
        st.header("Settings & Account Management")
        with st.form("update_password"):
            new_pass = st.text_input("New Password", type="password")
            confirm = st.text_input("Confirm New Password", type="password")
            if st.form_submit_button("Update Password"):
                if new_pass == confirm:
                    db.update_password(st.session_state.user_id, new_pass)
                    st.success("Password updated!")
                else:
                    st.error("Passwords do not match")
        st.subheader("2FA Setup")
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
            st.subheader("Admin Control Center")
            st.write("Manage Users & Payments")
            all_users = db.get_all_users()
            user_df = pd.DataFrame(all_users)
            st.dataframe(user_df[['user_id', 'email', 'is_premium', 'is_banned']], hide_index=True)
            for user in all_users:
                col1, col2, col3, col4, col5 = st.columns(5)
                with col1:
                    st.write(f"User: {user['email']} (ID: {user['user_id']})")
                with col2:
                    if st.button("Ban", key=f"ban_{user['user_id']}"):
                        db.ban_user(user['user_id'])
                        st.rerun()
                with col3:
                    if st.button("Unban", key=f"unban_{user['user_id']}"):
                        db.unban_user(user['user_id'])
                        st.rerun()
                with col4:
                    if st.button("Upgrade to Premium", key=f"upgrade_{user['user_id']}"):
                        db.upgrade_to_premium(user['user_id'])
                        st.rerun()
                with col5:
                    if st.button("Downgrade to Basic", key=f"downgrade_{user['user_id']}"):
                        db.downgrade_to_basic(user['user_id'])
                        st.rerun()
            st.subheader("Pending Payments Table")
            payments = db.get_pending_payments()
            if payments:
                payments_df = pd.DataFrame(payments)
                st.dataframe(payments_df[['id', 'user_id', 'phone', 'mpesa_code', 'timestamp']], hide_index=True)
            for p in payments:
                st.write(f"User {p['user_id']} | Phone: {p['phone']} | Code: {p['mpesa_code']}")
                if st.button("Approve", key=f"approve_{p['id']}"):
                    db.approve_payment(p["id"])
                    st.rerun()

else:
    st.session_state.page = "landing"
    st.rerun()
