# app.py — FULL REWRITE: All Features + 2FA in Login Flow + Admin Fix
import streamlit as st
import bcrypt
import pandas as pd
import plotly.express as px
import re
import io
import PyPDF2
import qrcode
import base64
import time
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES
from utils import VoiceInputHelper, Translator_Utils, cached_pdf_extract

LEVELS = {1: 0, 2: 100, 3: 250, 4: 500, 5: 1000}
XP_RULES = {"question_asked": 10, "pdf_question": 15, "quiz_generated": 5, "essay_5_percent": 1, "2fa_enabled": 20}

st.set_page_config(page_title='Kenyan EdTech', layout='wide')

db = Database()
db.auto_downgrade()

real_ai = AIEngine(st.secrets.get('GEMINI_API_KEY', ''))
ai_engine = real_ai if getattr(real_ai, 'gemini_key', None) else LocalFallbackAI()

if 'initialized' not in st.session_state:
    st.session_state.update({'logged_in': False, 'user_id': None, 'user': None, 'chat_history': [], 'pdf_text': '', 'show_qr': False, 'secret_key': None, 'qr_code': None, 'current_subject': 'Mathematics', 'lang': 'en', 'show_2fa': False, 'temp_user_id': None})

translator = Translator_Utils()

def get_user(force_reload=False):
    if st.session_state.user_id and (force_reload or not st.session_state.user):
        st.session_state.user = db.get_user(st.session_state.user_id)
    return st.session_state.user

def award_xp(user_id, points, reason):
    db.add_xp(user_id, points)
    get_user(force_reload=True)
    try: st.toast(f'+{points} XP — {reason}')
    except: st.success(f'+{points} XP — {reason}')

def safe_add_chat(user_id, subject, user_msg, ai_msg):
    try:
        db.add_chat_history(user_id, subject, user_msg, ai_msg)
    except Exception:
        pass

with st.sidebar:
    st.title('Kenyan EdTech')
    if st.session_state.logged_in:
        u = get_user()
        if u:
            crown = "Crown" if u.get('username') == 'EmperorUnruly' else "Brain"
            st.image(f"https://img.icons8.com/fluency/100/000000/{crown.lower()}.png", width=100)
            st.markdown(f"**XP:** {u.get('total_xp',0):,}")
            st.markdown(f"**Spendable:** {u.get('spendable_xp',0):,}")
            st.markdown(f"**XP Coins:** {u.get('xp_coins',0):,}")
            st.markdown(f"**Streak:** {u.get('streak',0)} days")
            if u.get('discount_20'): st.success("20% Discount Active!")

def chat_tab():
    st.header(f"Chat Tutor — {st.session_state.current_subject}")
    for m in st.session_state.chat_history: st.write(m['role'], m['content'])
    prompt = st.chat_input('Ask a question')
    if prompt:
        with st.spinner('Thinking...'):
            sys_prompt = get_enhanced_prompt(st.session_state.current_subject, prompt)
            resp = ai_engine.generate_response(prompt, sys_prompt)
        st.session_state.chat_history.append({'role': 'user', 'content': prompt})
        st.session_state.chat_history.append({'role': 'assistant', 'content': resp})
        safe_add_chat(st.session_state.user_id, st.session_state.current_subject, prompt, resp)
        award_xp(st.session_state.user_id, XP_RULES['question_asked'], 'Chat question')

def settings_tab():
    st.header('Settings')
    uid = st.session_state.user_id
    st.markdown('### Two-Factor Authentication')
    if db.is_2fa_enabled(uid) and not st.session_state.get('show_qr'):
        st.success('2FA Enabled')
        if st.button('Disable 2FA'): db.disable_2fa(uid); st.success('Disabled'); st.rerun()
    else:
        if st.session_state.get('show_qr'):
            qr = st.session_state.get('qr_code')
            secret = st.session_state.get('secret_key')
            if qr:
                b64 = base64.b64encode(qr).decode()
                st.image(f"data:image/png;base64,{b64}")
            if secret: st.code(secret)
            code = st.text_input('Enter 2FA code')
            if st.button('Confirm'):
                if db.verify_2fa_code(uid, code): st.success('2FA enabled'); st.session_state.show_qr = False; award_xp(uid, XP_RULES['2fa_enabled'], '2FA'); st.rerun()
                else: st.error('Invalid code')
        else:
            if st.button('Enable 2FA'):
                secret, qr = db.enable_2fa(uid)
                st.session_state.secret_key = secret
                st.session_state.qr_code = qr
                st.session_state.show_qr = True
                st.rerun()

def pdf_tab():
    st.header('PDF Q&A')
    uploaded = st.file_uploader('Upload a PDF', type='pdf')
    if uploaded:
        data = uploaded.getvalue()
        st.session_state.pdf_text = cached_pdf_extract(data, uploaded.name)
        st.success(f'Loaded {uploaded.name}')
        if st.checkbox('Show snippet'): st.code(st.session_state.pdf_text[:1000])
        q = st.chat_input('Ask about PDF')
        if q:
            resp = ai_engine.generate_response(q, get_enhanced_prompt(st.session_state.current_subject, q, context=f"Doc:{st.session_state.pdf_text[:10000]}"))
            st.write(resp)
            db.increment_daily_pdf(st.session_state.user_id)
            award_xp(st.session_state.user_id, XP_RULES['pdf_question'], 'PDF Q')

def progress_tab():
    st.header('Progress')
    u = get_user()
    if not u: st.info('No user'); return
    st.write('Total XP:', u.get('total_xp',0)); st.write('Spendable:', u.get('spendable_xp',0))
    lb = db.get_xp_leaderboard()
    if lb: st.dataframe(pd.DataFrame([dict(r) for r in lb]))

def exam_tab():
    st.header('Exam Prep')
    exam_type = st.selectbox('Exam Type', list(EXAM_TYPES.keys()))
    subjects = EXAM_TYPES[exam_type]['subjects']
    subject = st.selectbox('Subject', subjects)
    mode = st.radio('Mode', ["General Questions", "Specific Topic", "Project"])
    if mode == "Specific Topic":
        topics = EXAM_TYPES[exam_type]['topics'].get(subject, [])
        topic = st.selectbox('Topic', topics)
    else:
        topic = ""
    num_questions = st.number_input('Number of Questions (Max 100)', min_value=1, max_value=100, value=5)
    if st.button('Generate'):
        questions = ai_engine.generate_exam_questions(subject, exam_type, num_questions, topic)
        st.session_state.questions = questions
        st.session_state.user_answers = {}
    if 'questions' in st.session_state:
        for i, q in enumerate(st.session_state.questions):
            st.write(q['question'])
            st.session_state.user_answers[i] = st.radio("", q['options'], key=f"q{i}")
        if st.button('Submit'):
            result = ai_engine.grade_mcq(st.session_state.questions, st.session_state.user_answers)
            st.write(result)
            db.add_score(st.session_state.user_id, "exam", result["percentage"])
            award_xp(st.session_state.user_id, int(result["percentage"]), 'Exam Score')

def essay_tab():
    st.header('Essay Grader')
    essay = st.text_area('Paste essay')
    rubric = st.text_input('Rubric')
    if st.button('Grade'):
        result = ai_engine.grade_essay(essay, rubric)
        st.write(result)

def shop_page():
    user = st.session_state.user
    st.header("XP Coin Shop")
    if st.button("Buy 20% Discount Cheque"):
        if db.buy_discount_cheque(user['user_id']):
            st.success("Success! 20% discount activated!")
            st.balloons()
        else:
            st.error("Not enough XP Coins!")

def emperor_panel():
    st.header("EmperorUnruly Control")
    for p in db.get_pending_payments():
        st.write(f"User {p['user_id']}: {p['mpesa_code']}")
        if st.button("Approve", key=p['id']):
            db.approve_payment(p['id'])
            st.rerun()

IMAGES = ["https://images.unsplash.com/photo-1524178232363-1fb2b075b655?w=1400"]

def landing():
    st.image(IMAGES[0], use_container_width=True)
    st.markdown("<h1 style='text-align:center;color:#FFD700;'>Kenyan EdTech</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align:center;color:#00ff9d;'>Kenya's Most Powerful AI Tutor</h3>", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1: st.button("Login", type="primary", use_container_width=True, on_click=lambda: st.session_state.update(login=True))
    with c2: st.button("Register", use_container_width=True, on_click=lambda: st.session_state.update(reg=True))
    if st.session_state.get('login') or st.session_state.get('reg'):
        with st.expander("Account Access", expanded=True):
            with st.form("auth"):
                u = st.text_input("Username")
                e = st.text_input("Email")
                p = st.text_input("Password", type="password")
                c1, c2 = st.columns(2)
                with c1:
                    if st.form_submit_button("Login"):
                        user = db.verify_login(u or e, p)
                        if user:
                            st.session_state.temp_user = user
                            st.session_state.show_2fa = db.is_2fa_enabled(user['user_id'])
                            st.rerun()
                        else: st.error("Invalid credentials")
                with c2:
                    if st.form_submit_button("Register"):
                        hashed = bcrypt.hashpw(p.encode(), bcrypt.gensalt())
                        try:
                            db.create_user(e, p, u)
                            st.success("Registered! Login now.")
                        except: st.error("Username or email taken")

if not st.session_state.logged_in:
    landing()
    if st.session_state.get('show_2fa'):
        code = st.text_input('Enter 2FA Code')
        if st.button('Verify'):
            if db.verify_2fa_code(st.session_state.temp_user['user_id'], code):
                st.session_state.logged_in = True
                st.session_state.user_id = st.session_state.temp_user['user_id']
                st.session_state.user = st.session_state.temp_user
                del st.session_state.temp_user
                del st.session_state.show_2fa
                st.rerun()
            else: st.error('Invalid code')
else:
    menu = ["Chat Tutor", "Progress", "Settings", "PDF Q&A", "Exam Prep", "Essay Grader", "Premium", "Shop", "Admin"]
    if st.session_state.user.get('username') == 'EmperorUnruly': menu.append("Emperor Panel")
    choice = st.sidebar.radio("Menu", menu)
    if choice == "Chat Tutor": chat_tab()
    elif choice == "Settings": settings_tab()
    elif choice == "PDF Q&A": pdf_tab()
    elif choice == "Progress": progress_tab()
    elif choice == "Exam Prep": exam_tab()
    elif choice == "Essay Grader": essay_tab()
    elif choice == "Shop": shop_page()
    elif choice == "Emperor Panel": emperor_panel()
    elif choice == "Premium":
        st.success("Send **KSh 600** (or **KSh 480 with 20% discount**) to **0701617120**")
        if st.session_state.user.get('discount_20'): st.info("You have 20% discount! Pay only KSh 480")
        with st.form("pay"):
            phone = st.text_input("Phone")
            code = st.text_input("M-Pesa Code")
            if st.form_submit_button("Submit"):
                db.add_payment(st.session_state.user_id, phone, code)
                st.balloons()
    else: st.info('Select a menu item')
