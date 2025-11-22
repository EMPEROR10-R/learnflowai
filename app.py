# app.py — Updated with topic selector, max 100 q, projects + gamification, voice input, Kiswahili toggle
import streamlit as st
import bcrypt
import json
import pandas as pd
import plotly.express as px
from datetime import date, timedelta
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES
import re
import io
import PyPDF2
import qrcode
import base64
import time
from utils import VoiceInputHelper, Translator_Utils  # Updated import

class LocalFallbackAI:
    def generate_response(self, prompt, system_instruction):
        p = prompt.lower()
        if any(word in p for word in ['calculate','solve','what is']):
            expr = re.search(r"([0-9\s\.+\-*/()]+)", prompt)
            try:
                if expr:
                    return f"(LocalAI) {eval(expr.group(1))}"
            except Exception:
                pass
        return "(LocalAI) Configure GEMINI_API_KEY in Streamlit secrets for full AI."
    def generate_exam_questions(self, subject, exam_type, num_questions, topic):
        return [{"question":f"Sample Q{i+1}", "options":["A","B","C","D"], "answer":"A","feedback":"Sample"} for i in range(num_questions)]
    def grade_mcq(self, questions, user_answers):
        correct=0; results=[]
        for i,q in enumerate(questions):
            ua=user_answers.get(i,'')
            is_correct = ua and ua.startswith(q.get('answer','')[0])
            if is_correct: correct+=1
            results.append({"question":q['question'],"user_answer":ua,"correct_answer":q.get('answer',''),"is_correct":is_correct,"feedback":q.get('feedback','')})
        total=len(questions); pct=int((correct/total)*100) if total else 0
        return {"correct":correct,"total":total,"percentage":pct,"results":results}
    def grade_essay(self, essay, rubric):
        words=len(essay.split()); score=min(90,max(30,int(words/1000*50)))
        return {"score":score,"feedback":f"Length-based (LocalAI). Words: {words}."}
    def grade_project(self, subject, project_name, submission):
        return {"score": 50, "feedback": "Fallback project grade.", "xp": 100}

LEVELS={1:0,2:100,3:250,4:500,5:1000}
BASIC_MAX_LEVEL=5
XP_RULES={"question_asked":10, "pdf_question":15, "quiz_generated":5, "essay_5_percent":1, "2fa_enabled":20, "project_completed":100}

st.set_page_config(page_title='Kenyan EdTech', layout='wide')

try:
    db=Database()
    db.auto_downgrade()
except Exception as e:
    st.error(f'DB init failed: {e}'); st.stop()

real_ai = AIEngine(st.secrets.get('GEMINI_API_KEY',''))
ai_engine = real_ai if getattr(real_ai,'gemini_key',None) else LocalFallbackAI()

if 'initialized' not in st.session_state:
    st.session_state.update({'logged_in':False,'user_id':None,'user':None,'chat_history':[],'pdf_text':'','show_qr':False,'secret_key':None,'qr_code':None,'current_subject':'Mathematics', 'lang':'en'})

def get_user():
    if not st.session_state.get('user_id'): return None
    st.session_state.user = db.get_user(st.session_state.user_id)
    return st.session_state.user

def award_xp(user_id, points, reason):
    db.add_xp(user_id, points)
    st.session_state.user = db.get_user(user_id)
    try: st.toast(f'+{points} XP — {reason}')
    except: st.success(f'+{points} XP — {reason}')

def safe_add_chat(user_id, subject, user_msg, ai_msg):
    try:
        db.add_chat_history(user_id, subject, user_msg, ai_msg)
        return
    except Exception:
        cur = db.conn.cursor()
        for cols in [('user_query','ai_response'), ('user_message','ai_response'), ('user_query','response')]:
            try:
                cur.execute(f"INSERT INTO chat_history (user_id, subject, {cols[0]}, {cols[1]}) VALUES (?,?,?,?)", (user_id, subject, user_msg, ai_msg))
                db.conn.commit(); return
            except Exception:
                db.conn.rollback()

translator = Translator_Utils()

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
    st.selectbox("Language", ["English", "Kiswahili"], key="lang", index=0 if st.session_state.lang == 'en' else 1)
    st.session_state.lang = 'sw' if st.session_state.lang == "Kiswahili" else 'en'

def chat_tab():
    st.header(translator.translate_text(f"Chat Tutor — {st.session_state.current_subject}", st.session_state.lang))
    for m in st.session_state.chat_history: st.write(m['role'], translator.translate_text(m['content'], st.session_state.lang))
    st.markdown(VoiceInputHelper.get_voice_input_html(), unsafe_allow_html=True)
    if st.button("Voice Input"): st.write("Speak now...")  # Triggers JS
    prompt = st.chat_input('Ask a question')
    if prompt:
        with st.spinner('Thinking...'):
            try:
                sys_prompt = get_enhanced_prompt(st.session_state.current_subject, prompt)
                resp = ai_engine.generate_response(prompt, sys_prompt)
            except Exception as e:
                resp = f'AI error: {e}'
        st.session_state.chat_history.append({'role':'user','content':prompt})
        st.session_state.chat_history.append({'role':'assistant','content':resp})
        safe_add_chat(st.session_state.user_id, st.session_state.current_subject, prompt, resp)
        award_xp(st.session_state.user_id, XP_RULES['question_asked'], 'Chat question')

def settings_tab():
    st.header(translator.translate_text('Settings', st.session_state.lang))
    uid = st.session_state.user_id
    st.markdown(translator.translate_text('### Two-Factor Authentication', st.session_state.lang))
    if db.is_2fa_enabled(uid) and not st.session_state.get('show_qr'):
        st.success(translator.translate_text('2FA Enabled', st.session_state.lang))
        if st.button(translator.translate_text('Disable 2FA', st.session_state.lang)): db.disable_2fa(uid); st.success('Disabled')
    else:
        if st.session_state.get('show_qr'):
            qr = st.session_state.get('qr_code')
            secret = st.session_state.get('secret_key')
            if not qr and secret:
                img = qrcode.make(f"otpauth://totp/Kenyan EdTech:{uid}?secret={secret}&issuer=Kenyan EdTech")
                buf = io.BytesIO(); img.save(buf,'PNG'); qr=buf.getvalue(); st.session_state.qr_code=qr
            if qr:
                b64=base64.b64encode(qr).decode(); st.image(f"data:image/png;base64,{b64}")
            if secret: st.code(secret)
            code = st.text_input(translator.translate_text('Enter 2FA code', st.session_state.lang))
            if st.button(translator.translate_text('Confirm', st.session_state.lang)):
                if db.verify_2fa_code(uid, code): st.success('2FA enabled'); st.session_state.show_qr=False; award_xp(uid, XP_RULES['2fa_enabled'],'2FA')
                else: st.error('Invalid code')
        else:
            if st.button(translator.translate_text('Enable 2FA', st.session_state.lang)):
                secret, qr = db.enable_2fa(uid)
                st.session_state.secret_key=secret; st.session_state.qr_code=qr; st.session_state.show_qr=True; st.success('Scan then confirm')

def pdf_tab():
    st.header(translator.translate_text('PDF Q&A', st.session_state.lang))
    uploaded = st.file_uploader(translator.translate_text('Upload a PDF', st.session_state.lang), type='pdf')
    if uploaded:
        try:
            data = uploaded.getvalue()
            st.session_state.pdf_text = cached_pdf_extract(data, uploaded.name)
            st.success(f'Loaded {uploaded.name}')
            if st.checkbox(translator.translate_text('Show snippet', st.session_state.lang)): st.code(st.session_state.pdf_text[:1000])
            q = st.chat_input(translator.translate_text('Ask about PDF', st.session_state.lang))
            if q:
                resp = ai_engine.generate_response(q, get_enhanced_prompt(st.session_state.current_subject, q, context=f"Doc:{st.session_state.pdf_text[:10000]}"))
                st.write(translator.translate_text(resp, st.session_state.lang))
                db.increment_daily_pdf(st.session_state.user_id)
                award_xp(st.session_state.user_id, XP_RULES['pdf_question'], 'PDF Q')
        except Exception as e:
            st.error(f'PDF error: {e}')

def progress_tab():
    st.header(translator.translate_text('Progress', st.session_state.lang))
    u = get_user()
    if not u: st.info('No user'); return
    st.write(translator.translate_text('Total XP:', st.session_state.lang), u.get('total_xp',0)); st.write('Spendable:', u.get('spendable_xp',0))
    lb = db.get_xp_leaderboard()
    if lb: st.dataframe(pd.DataFrame([dict(r) for r in lb]))
    st.subheader(translator.translate_text('Your Projects', st.session_state.lang))
    projects = db.get_user_projects(u['user_id'])
    if projects:
        st.table(projects)
    else:
        st.info(translator.translate_text('No projects submitted yet.', st.session_state.lang))

def exam_tab():
    st.header(translator.translate_text('Exam Prep', st.session_state.lang))
    exam_type = st.selectbox(translator.translate_text('Exam Type', st.session_state.lang), list(EXAM_TYPES.keys()))
    subjects = EXAM_TYPES[exam_type]['subjects']
    subject = st.selectbox(translator.translate_text('Subject', st.session_state.lang), subjects)
    mode = st.radio(translator.translate_text('Mode', st.session_state.lang), ["General Questions", "Specific Topic", "Project"])
    if mode == "Specific Topic":
        topics = EXAM_TYPES[exam_type]['topics'].get(subject, [])
        topic = st.selectbox(translator.translate_text('Topic', st.session_state.lang), topics)
    else:
        topic = ""
    num_questions = st.number_input(translator.translate_text('Number of Questions (Max 100)', st.session_state.lang), min_value=1, max_value=100, value=5)
    if st.button(translator.translate_text('Generate', st.session_state.lang)):
        questions = ai_engine.generate_exam_questions(subject, exam_type, num_questions, topic)
        st.session_state.questions = questions
        st.session_state.user_answers = {}
    if 'questions' in st.session_state:
        for i, q in enumerate(st.session_state.questions):
            st.write(translator.translate_text(q['question'], st.session_state.lang))
            st.session_state.user_answers[i] = st.radio("", q['options'], key=f"q{i}")
        if st.button(translator.translate_text('Submit Exam', st.session_state.lang)):
            result = ai_engine.grade_mcq(st.session_state.questions, st.session_state.user_answers)
            st.write(result)
            award_xp(st.session_state.user_id, result['percentage'], 'Exam Score')

def project_tab():
    st.header(translator.translate_text('Project Mode', st.session_state.lang))
    exam_type = st.selectbox(translator.translate_text('Exam Type', st.session_state.lang), [k for k in EXAM_TYPES if EXAM_TYPES[k]['projects']])
    subjects = [s for s in EXAM_TYPES[exam_type]['subjects'] if s in EXAM_TYPES[exam_type]['projects']]
    subject = st.selectbox(translator.translate_text('Subject', st.session_state.lang), subjects)
    project_name = st.selectbox(translator.translate_text('Project', st.session_state.lang), EXAM_TYPES[exam_type]['projects'].get(subject, "").split(", "))
    submission = st.text_area(translator.translate_text('Submit your project (code/text/description)', st.session_state.lang))
    if st.button(translator.translate_text('Grade Project', st.session_state.lang)):
        result = ai_engine.grade_project(subject, project_name, submission)
        st.write(result)
        db.submit_project(st.session_state.user_id, subject, project_name, submission, result['score'], result['xp'])
        award_xp(st.session_state.user_id, result['xp'], 'Project Completion')

def essay_tab():
    st.header(translator.translate_text('Essay Grader', st.session_state.lang))
    essay = st.text_area(translator.translate_text('Paste essay', st.session_state.lang))
    rubric = st.text_input(translator.translate_text('Rubric', st.session_state.lang))
    if st.button(translator.translate_text('Grade', st.session_state.lang)):
        result = ai_engine.grade_essay(essay, rubric)
        st.write(result)

def admin_tab(): st.header('Admin'); st.info('Admin panel')

def shop_page():
    user = st.session_state.user
    st.header(translator.translate_text("XP Coin Shop", st.session_state.lang))
    if st.button(translator.translate_text("Buy 20% Discount Cheque", st.session_state.lang)):
        if db.buy_discount_cheque(user['user_id']):
            st.success(translator.translate_text("Success! 20% discount activated!", st.session_state.lang))
            st.balloons()
        else:
            st.error(translator.translate_text("Not enough XP Coins!", st.session_state.lang))

def emperor_panel():
    st.header("EmperorUnruly Control")
    for p in db.conn.execute("SELECT p.*, u.username FROM payments p JOIN users u ON p.user_id=u.user_id WHERE status='pending'").fetchall():
        c1,c2,c3 = st.columns([3,2,1])
        c1.write(f"**{p['username']}** • {p['phone']} • `{p['mpesa_code']}`")
        if c3.button("Approve", key=p['id']): db.approve_payment(p['id']); st.rerun()

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
                        user_row = db.conn.execute("SELECT * FROM users WHERE username=? OR email=?", (u, e)).fetchone()
                        if user_row and bcrypt.checkpw(p.encode(), user_row['password_hash']):
                            st.session_state.update(logged_in=True, user_id=user_row['user_id'], user=dict(user_row))
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
else:
    menu = ["Chat Tutor", "Progress", "Settings", "PDF Q&A", "Exam Prep", "Project Mode", "Essay Grader", "Premium", "Shop", "Admin"]
    if st.session_state.user.get('username') == 'EmperorUnruly': menu.append("Emperor Panel")
    choice = st.sidebar.radio("Menu", menu)

    if choice == "Chat Tutor": chat_tab()
    elif choice == "Settings": settings_tab()
    elif choice == "PDF Q&A": pdf_tab()
    elif choice == "Progress": progress_tab()
    elif choice == "Exam Prep": exam_tab()
    elif choice == "Project Mode": project_tab()  # New tab
    elif choice == "Essay Grader": essay_tab()
    elif choice == "Admin": admin_tab()
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

    mapping = {'Chat Tutor':chat_tab, 'Progress':progress_tab, 'Settings':settings_tab, 'PDF Q&A':pdf_tab, 'Exam Prep':exam_tab, 'Project Mode':project_tab, 'Essay Grader':essay_tab, 'Premium': lambda: st.info('Premium'), 'Admin':admin_tab}
    tabs = list(mapping.keys())
    for name, tab in zip(tabs, st.tabs(tabs)):
        st.session_state.current_subject = st.session_state.get('current_subject','Mathematics')
        try:
            mapping.get(name, lambda: st.info('Unknown'))()
        except Exception as e:
            st.error(f'Tab {name} failed but others continue: {e}')
