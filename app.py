# app.py
import streamlit as st
import bcrypt
import json
import pandas as pd
from datetime import datetime
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES

st.set_page_config(page_title="LearnFlow AI", page_icon="KE", layout="wide")

try:
    db = Database()
    ai_engine = AIEngine(st.secrets.get("GEMINI_API_KEY", ""))
except Exception as e:
    st.error(f"INIT FAILED: {e}")
    st.stop()

def init_session():
    defaults = {
        "logged_in": False, "user_id": None, "is_admin": False, "user": None,
        "show_welcome": True, "chat_history": [], "current_subject": "Mathematics",
        "is_parent": False, "pdf_text": "", "current_tab": "Chat Tutor"
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

def get_user_tier():
    if st.session_state.is_admin: return "admin"
    if db.check_premium(st.session_state.user_id) and db.check_premium_validity(st.session_state.user_id): return "premium"
    return "basic"

def enforce_access():
    tier = get_user_tier()
    if tier == "basic" and st.session_state.current_tab not in ["Chat Tutor", "Settings"]:
        st.warning("Upgrade to Premium to access this feature.")
        st.stop()
    if tier == "basic" and not db.can_ask_question(st.session_state.user_id):
        st.error("Daily limit: 10 questions. Upgrade to Premium!")
        st.stop()

# UI
def welcome_screen():
    st.markdown('<div style="background:linear-gradient(135deg,#009E60,#FFD700);padding:50px;border-radius:20px;color:white;text-align:center">'
                '<h1>LearnFlow AI</h1><p>Your Kenyan AI Tutor</p><p>KCPE • KPSEA • KJSEA • KCSE</p></div>', unsafe_allow_html=True)
    _, c, _ = st.columns([1,1,1])
    with c:
        if st.button("Start Learning!", type="primary", use_container_width=True):
            st.session_state.show_welcome = False
            st.rerun()

def login_block():
    if st.session_state.logged_in: return
    st.markdown("### Login / Sign Up")
    choice = st.radio("Action", ["Login", "Sign Up"], horizontal=True, label_visibility="collapsed")
    email = st.text_input("Email", key=f"{choice.lower()}_email")
    pwd = st.text_input("Password", type="password", key=f"{choice.lower()}_pwd")
    totp = st.text_input("2FA Code", key="totp") if choice == "Login" else ""
    if st.button(choice, type="primary"):
        if len(pwd) < 6: st.error("Password ≥6 chars")
        elif choice == "Sign Up":
            uid = db.create_user(email, pwd)
            st.success("Created! Log in.") if uid else st.error("Email taken")
        else:
            user = db.get_user_by_email(email)
            if not user or not bcrypt.checkpw(pwd.encode(), user["password_hash"].encode()):
                st.error("Wrong credentials")
            elif db.is_2fa_enabled(user["user_id"]) and not db.verify_2fa_code(user["user_id"], totp):
                st.error("Bad 2FA")
            else:
                db.update_user_activity(user["user_id"])
                st.session_state.update({
                    "logged_in": True, "user_id": user["user_id"],
                    "is_admin": user["role"] == "admin", "user": user,
                    "is_parent": bool(user.get("parent_id"))
                })
                st.rerun()

def sidebar():
    with st.sidebar:
        st.markdown("## LearnFlow AI")
        tier = get_user_tier()
        st.markdown(f"**Tier:** {tier.upper()}")
        if tier == "basic": st.warning("10 Qs/day | Chat + Settings only")
        user = db.get_user(st.session_state.user_id) or {}
        streak = db.update_streak(st.session_state.user_id)
        st.markdown(f"**Streak:** {streak} days")
        st.session_state.current_subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()), key="subj")
        badges_raw = user.get("badges", "[]")
        try: badges = json.loads(badges_raw) if isinstance(badges_raw, str) else badges_raw
        except: badges = []
        for b in badges[:5]: st.markdown(f"{BADGES.get(b, b)}")
        lb = db.get_leaderboard("exam")[:3]
        st.markdown("### Leaderboard")
        for i, e in enumerate(lb): st.markdown(f"**{i+1}.** {e['email']} – {e['score']:.0f}")

# TABS
def chat_tab():
    st.session_state.current_tab = "Chat Tutor"
    enforce_access()
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
    if prompt := st.chat_input("Ask..."):
        if not db.can_ask_question(st.session_state.user_id):
            st.error("Daily limit reached.")
            return
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                context = st.session_state.pdf_text[-2000:] if st.session_state.pdf_text else ""
                resp = ai_engine.generate_response(prompt, get_enhanced_prompt(st.session_state.current_subject, prompt, context))
                st.markdown(resp)
                st.session_state.chat_history.append({"role": "assistant", "content": resp})
        db.add_chat_history(st.session_state.user_id, st.session_state.current_subject, prompt, resp)
        db.add_score(st.session_state.user_id, "chat", 10)

def pdf_tab():
    st.session_state.current_tab = "PDF Q&A"
    enforce_access()
    file = st.file_uploader("Upload PDF", type="pdf", key="pdf")
    if file and not st.session_state.pdf_text:
        with st.spinner("Reading..."):
            text = ai_engine.extract_text_from_pdf(file.read())
            st.session_state.pdf_text = text
            st.success("PDF loaded!")
    if st.session_state.pdf_text:
        if q := st.chat_input("Ask about PDF..."):
            with st.chat_message("user"): st.markdown(q)
            with st.chat_message("assistant"):
                with st.spinner("Answering..."):
                    resp = ai_engine.generate_response(q, f"Text:\n{st.session_state.pdf_text[-3000:]}")
                    st.markdown(resp)

def exam_tab():
    st.session_state.current_tab = "Exam Prep"
    enforce_access()
    if "exam_questions" not in st.session_state:
        exam_type = st.selectbox("Exam Type", list(EXAM_TYPES.keys()), key="etype")
        subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()), key="esubj")
        num = st.slider("Questions", 1, 100, 10, key="enum")
        if st.button("Generate", key="gen"):
            st.session_state.exam_questions = ai_engine.generate_exam_questions(subject, exam_type, num)
            st.session_state.user_answers = {}
            st.rerun()
    else:
        for i, q in enumerate(st.session_state.exam_questions):
            st.markdown(f"**Q{i+1}:** {q['question']}")
            st.session_state.user_answers[i] = st.radio("Choose", q['options'], key=f"ans_{i}")
        if st.button("Submit", key="sub"):
            res = ai_engine.grade_mcq(st.session_state.exam_questions, st.session_state.user_answers)
            score = res["percentage"]
            db.add_score(st.session_state.user_id, "exam", score)
            if score >= 90: db.add_badge(st.session_state.user_id, "exam_master")
            st.markdown(f"**Score: {score}%**")
            for r in res["results"]:
                icon = "Correct" if r["is_correct"] else "Wrong"
                st.markdown(f"- {icon} **{r['question']}**  \n  Your: `{r['user_answer']}`  \n  Correct: `{r['correct_answer']}`")
            del st.session_state.exam_questions

def essay_tab():
    st.session_state.current_tab = "Essay Grader"
    enforce_access()
    essay = st.text_area("Essay", height=200, key="essay")
    if st.button("Grade", key="grade") and essay.strip():
        res = ai_engine.grade_essay(essay, "Kenyan curriculum")
        score = res["score"]
        db.add_score(st.session_state.user_id, "essay", score)
        if score >= 90: db.add_badge(st.session_state.user_id, "essay_expert")
        st.markdown(f"**Score: {score}/100** – {res['feedback']}")

def premium_tab():
    st.session_state.current_tab = "Premium"
    if st.session_state.is_admin:
        st.success("Admin has full access.")
        return
    discount = db.get_user(st.session_state.user_id).get("discount", 0)
    price = 500 * (1 - discount)
    st.markdown(f"### Price: **KES {price:.0f}**")
    if discount: st.success("20% Leaderboard Discount!")
    st.info("Send to M-Pesa: `0701617120`")
    phone = st.text_input("Phone", key="pphone")
    code = st.text_input("Code", key="pcode")
    if st.button("Submit", key="psub"):
        db.add_manual_payment(st.session_state.user_id, phone, code)
        st.success("Submitted!")

def admin_dashboard():
    st.session_state.current_tab = "Admin"
    if not st.session_state.is_admin:
        st.error("Access denied.")
        return
    st.markdown("## Admin Control Centre")
    if st.button("Apply Monthly Discounts"):
        db.apply_monthly_discount()
        st.success("20% discount given to champions!")
    payments = db.get_pending_payments()
    if payments:
        for p in payments:
            col1, col2, col3 = st.columns([3,1,1])
            with col1: st.write(f"{p['phone']} – {p['mpesa_code']}")
            with col2: 
                if st.button("Approve", key=f"a{p['id']}"):
                    db.approve_manual_payment(p['id'])
                    st.rerun()
            with col3:
                if st.button("Reject", key=f"r{p['id']}"):
                    db.reject_manual_payment(p['id'])
                    st.rerun()
    users = db.get_all_users()
    if users: st.dataframe(pd.DataFrame(users)[["email", "name", "role", "is_premium"]])

def main():
    try:
        init_session()
        if st.session_state.show_welcome: welcome_screen(); return
        login_block()
        if not st.session_state.logged_in: st.info("Log in."); return
        sidebar()
        enforce_access()
        tabs = ["Chat Tutor", "PDF Q&A", "Exam Prep", "Essay Grader", "Settings"]
        if get_user_tier() == "basic": tabs = ["Chat Tutor", "Settings"]
        if get_user_tier() != "premium" and not st.session_state.is_admin: tabs.append("Premium")
        if st.session_state.is_admin: tabs.append("Admin Control Centre")
        tab_objs = st.tabs(tabs)
        with tab_objs[0]: chat_tab()
        if len(tabs) > 1 and "PDF Q&A" in tabs: 
            with tab_objs[tabs.index("PDF Q&A")]: pdf_tab()
        if "Exam Prep" in tabs: 
            with tab_objs[tabs.index("Exam Prep")]: exam_tab()
        if "Essay Grader" in tabs: 
            with tab_objs[tabs.index("Essay Grader")]: essay_tab()
        if "Premium" in tabs: 
            with tab_objs[tabs.index("Premium")]: premium_tab()
        if "Admin Control Centre" in tabs: 
            with tab_objs[tabs.index("Admin Control Centre")]: admin_dashboard()
    except Exception as e:
        st.error(f"CRASH: {e}")

if __name__ == "__main__":
    main()
