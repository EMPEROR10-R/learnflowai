# app.py — KENYAN EDTECH FINAL 2025 | PERFECTED | RICH XP SHOP | ALL SUBJECTS
import streamlit as st
import bcrypt
import pandas as pd
from datetime import datetime, date, timedelta
from database import Database
from ai_engine import AIEngine
from prompts import EXAM_TYPES, SUBJECT_PROMPTS

st.set_page_config(page_title="Kenyan EdTech", layout="wide", initial_sidebar_state="expanded")

# ======================== INIT ========================
db = Database()
db.auto_downgrade()
ai_engine = AIEngine()

# Session state
for key, default in {
    "logged_in": False, "user_id": None, "user": None, "page": "landing",
    "chat_history": [], "questions": [], "user_answers": {}, "pdf_text": ""
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ======================== STYLE ========================
st.markdown("""
<style>
    .hero {background: linear-gradient(135deg, #000, #006400, #FFD700, #C00);
           padding: 100px; border-radius: 25px; text-align: center; margin: -90px auto 40px;}
    .title {font-size: 5.5rem; color: gold; font-weight: bold;}
    .subtitle {font-size: 2.5rem; color: white;}
    .shop-card {background: #111; padding: 20px; border-radius: 15px; margin: 10px 0; border: 2px solid gold;}
</style>
<div class="hero">
    <h1 class="title">KENYAN EDTECH</h1>
    <p class="subtitle">Kenya's #1 AI Exam Prep Platform</p>
</div>
""", unsafe_allow_html=True)

# ======================== HELPERS ========================
def get_user():
    if st.session_state.user_id:
        st.session_state.user = db.get_user(st.session_state.user_id)
    return st.session_state.user

def award_xp(points, reason):
    if st.session_state.user_id:
        db.add_xp(st.session_state.user_id, points)
        get_user()
        st.toast(f"+{points} XP & Coins — {reason}", icon="🎉")

# ======================== AUTH ========================
if not st.session_state.logged_in:
    if st.session_state.page == "landing":
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            if st.button("LOGIN", use_container_width=True, type="primary"):
                st.session_state.page = "login"; st.rerun()
            if st.button("REGISTER FREE", use_container_width=True):
                st.session_state.page = "register"; st.rerun()

    elif st.session_state.page == "login":
        st.title("Login")
        with st.form("login"):
            email = st.text_input("Email")
            pwd = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                user = db.get_user_by_email(email)
                if user and bcrypt.checkpw(pwd.encode(), user["password_hash"]):
                    st.session_state.logged_in = True
                    st.session_state.user_id = user["user_id"]
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("Invalid credentials")

    elif st.session_state.page == "register":
        st.title("Register")
        with st.form("register"):
            email = st.text_input("Email")
            pwd = st.text_input("Password", type="password")
            confirm = st.text_input("Confirm Password", type="password")
            if pwd != confirm and pwd:
                st.error("Passwords do not match")
            if st.form_submit_button("Create Account"):
                if db.create_user(email, pwd):
                    st.success("Account created! Login now.")
                    st.session_state.page = "login"
                    st.rerun()
                else:
                    st.error("Email already exists")

else:
    user = get_user()
    is_emperor = user["email"] == "kingmumo15@gmail.com"

    # Sidebar
    with st.sidebar:
        st.success(f"Welcome, {user['username'] or user['email'].split('@')[0]}")
        st.metric("Level", user.get("level", 1))
        st.metric("XP Coins", f"{user.get('xp_coins', 0):,}")
        if is_emperor:
            st.balloons()
            st.success("EMPEROR MODE")
        elif user.get("is_premium"):
            st.info("Premium Active")
        if st.button("Logout"):
            st.session_state.clear()
            st.rerun()

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "AI Tutor", "Exam Prep", "PDF Q&A", "Progress", "XP Shop", "Premium", "Admin"
    ])

    with tab1:
        st.header("AI Tutor")
        subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))
        for msg in st.session_state.chat_history:
            st.chat_message(msg["role"]).write(msg["content"])
        if prompt := st.chat_input("Ask anything..."):
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            with st.chat_message("assistant"):
                with st.spinner("Thinking..."):
                    response = ai_engine.generate_response(prompt, SUBJECT_PROMPTS[subject])
                st.write(response)
            st.session_state.chat_history.append({"role": "assistant", "content": response})
            award_xp(10, "AI Question")

    with tab2:
        st.header("Exam Practice — Fresh AI Questions")
        exam = st.selectbox("Exam", ["KPSEA", "KJSEA", "KCSE"])
        subjects = EXAM_TYPES[exam]["subjects"]
        subject = st.selectbox("Subject", subjects)
        topics = EXAM_TYPES[exam]["topics"].get(subject, ["General"])
        topic = st.selectbox("Topic", topics)
        count = st.slider("Questions", 10, 100, 30)

        today = date.today().isoformat()
        used = user.get("daily_questions_used", 0) if user.get("last_question_date") == today else 0
        limit = 250 if user.get("is_premium") else 200
        remaining = limit - used

        st.info(f"Daily Limit: {limit} • Remaining: {remaining}")

        if st.button("Generate Exam", type="primary"):
            if count > remaining:
                st.error(f"Only {remaining} questions left today!")
            else:
                with st.spinner("AI generating fresh questions..."):
                    questions = ai_engine.generate_exam_questions(subject, exam, count, topic)
                if questions:
                    st.session_state.questions = questions
                    st.session_state.user_answers = {}
                    db.conn.execute("UPDATE users SET daily_questions_used=?, last_question_date=? WHERE user_id=?",
                                    (used + count, today, user["user_id"]))
                    db.conn.commit()
                    st.success(f"{len(questions)} unique questions loaded!")
                else:
                    st.error("Generation failed. Try again.")

        if st.session_state.questions:
            for i, q in enumerate(st.session_state.questions):
                st.write(f"**Q{i+1}.** {q['question']}")
                ans = st.radio("Choose", q["options"], key=f"q{i}")
                st.session_state.user_answers[i] = ans

            if st.button("Submit Exam", type="primary"):
                result = ai_engine.grade_mcq(st.session_state.questions, st.session_state.user_answers)
                st.success(f"Score: {result['score']}/{result['total']} ({result['percentage']}%)")
                if result['percentage'] >= 80:
                    st.balloons()
                xp = int(result['percentage'] * 2) + 100
                award_xp(xp, "Exam Completed")
                st.session_state.questions = []

    with tab5:
        st.header("XP Shop — Spend Your Hard-Earned Coins!")
        coins = user.get("xp_coins", 0)

        shop_items = [
            ("20% Lifetime Discount on Premium", 5_000_000, "shop_discount", "Get 20% off forever (KSh 480 instead of 600)"),
            ("+50 Extra Daily Questions", 800_000, "extra_questions", "Permanently increase daily limit by 50"),
            ("Custom Badge (Display Name)", 600_000, "custom_badge", "Show a unique badge next to your name"),
            ("+100 Extra AI Tutor Uses", 400_000, "extra_ai_uses", "More AI interactions per day"),
            ("Premium Profile Theme", 350_000, "profile_theme", "Unlock golden/dark theme"),
            ("Double XP for 7 Days", 700_000, None, "All XP gains doubled for one week"),
            ("Remove Ads Forever", 300_000, None, "Clean experience (future-proof)"),
            ("Shoutout on Leaderboard", 250_000, None, "Your name highlighted for 30 days"),
            ("Mystery Gift Box", 100_000, None, "Random reward: XP, coins, or premium trial"),
            ("Support the App (Donation)", 50_000, None, "Help us grow — thank you!")
        ]

        for name, base_price, field, desc in shop_items:
            purchases = db.conn.execute("SELECT COUNT(*) FROM purchases WHERE user_id=? AND item_name=?", (user["user_id"], name)).fetchone()[0]
            price = base_price * (2 ** purchases)  # Exponential pricing

            with st.container():
                st.markdown(f"<div class='shop-card'>", unsafe_allow_html=True)
                col1, col2 = st.columns([3,1])
                with col1:
                    st.subheader(name)
                    st.caption(desc)
                    st.write(f"**Price: {price:,} XP Coins** (x{purchases+1} purchased)")
                with col2:
                    if st.button("Buy", key=f"buy_{name}_{purchases}"):
                        if coins >= price:
                            db.spend_xp_coins(user["user_id"], price)
                            db.log_purchase(user["user_id"], name, price)
                            if field:
                                if field == "custom_badge":
                                    badge = st.text_input("Enter your badge text", key=f"badge_{name}")
                                    if badge:
                                        db.conn.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (badge, user["user_id"]))
                                        db.conn.commit()
                                else:
                                    current = user.get(field, 0)
                                    db.conn.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (current + 1, user["user_id"]))
                                    db.conn.commit()
                            st.success(f"Purchased {name}!")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("Not enough XP Coins")
                st.markdown("</div>", unsafe_allow_html=True)

    with tab6:
        st.header("Go Premium")
        if is_emperor:
            st.success("Emperor — Unlimited Access")
        elif user.get("is_premium"):
            st.success("Premium Active")
        else:
            price = 480 if user.get("shop_discount", 0) > 0 else 600
            st.info(f"Send **KSh {price}** to **0701617120** via M-Pesa")
            with st.form("payment"):
                phone = st.text_input("Your Phone Number")
                code = st.text_input("M-Pesa Transaction Code")
                if st.form_submit_button("Submit"):
                    db.add_payment(user["user_id"], phone, code)
                    st.success("Payment submitted! Waiting for approval.")

    with tab7:
        if is_emperor:
            st.header("Admin Panel")
            for u in db.conn.execute("SELECT user_id, email, is_premium FROM users").fetchall():
                u_dict = db.get_user(u["user_id"])
                with st.expander(f"{u_dict['email']} • {'Premium' if u_dict['is_premium'] else 'Free'}"):
                    c1,c2,c3 = st.columns(3)
                    with c1: st.button("Ban", key=f"ban{u['user_id']}"); db.ban_user(u["user_id"])
                    with c2: st.button("Premium", key=f"prem{u['user_id']}"); db.upgrade_to_premium(u["user_id"])
                    with c3: st.button("Basic", key=f"basic{u['user_id']}"); db.downgrade_to_basic(u["user_id"])
            st.subheader("Pending Payments")
            for p in db.get_pending_payments():
                if st.button(f"Approve {p['mpesa_code']} (User {p['user_id']})"):
                    db.approve_payment(p["id"])
                    st.success("Approved!")
        else:
            st.write("Access restricted.")