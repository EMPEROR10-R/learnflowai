# app.py
import streamlit as st
import bcrypt
import json
import pandas as pd
import plotly.express as px
from datetime import datetime, date, timedelta
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES
import pyotp 
import time
from typing import Optional, List, Dict
import io
import re
import PyPDF2 
import qrcode
import base64

# --- UTILS PLACEHOLDER (Using PyPDF2 for extraction) ---
class PDFParser:
    @staticmethod
    def extract_text(pdf_file) -> Optional[str]:
        try:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text.strip()
        except Exception as e:
            st.error(f"Error reading PDF: {str(e)}")
            return None

@st.cache_data
def cached_pdf_extract(file_bytes: bytes, filename: str) -> str:
    pdf_file = io.BytesIO(file_bytes)
    text = PDFParser.extract_text(pdf_file)
    return text if text is not None else "Error extracting PDF."
# -------------------------

# ────────────────────────────── CONFIG ──────────────────────────────
DEFAULT_ADMIN_EMAIL = "kingmumo15@gmail.com"
DEFAULT_ADMIN_PASSWORD = "@Yoounruly10"

# ==============================================================================
# GAMIFICATION: LEVELS + XP SYSTEM
# ==============================================================================
LEVELS = {
    1: 0, 2: 100, 3: 250, 4: 500, 5: 1000,
    6: 2000, 7: 3500, 8: 6000, 9: 10000, 10: 15000,
    11: 25000, 12: 40000, 13: 60000, 14: 90000, 15: 130000
}

BASIC_MAX_LEVEL = 5 

# XP EARNING RULES (Education-Focused)
XP_RULES = {
    "question_asked": 10,
    "pdf_upload": 30,
    "pdf_question": 15,
    "quiz_generated": 5, 
    "exam_10_percent": 1,  
    "essay_5_percent": 1, 
    "perfect_score": 100,
    "daily_streak": 20,
    "first_login": 50,
    "2fa_enabled": 20,
    "profile_complete": 30,
    "badge_earned": 50,
    "leaderboard_top3": 200,
    "discount_cheque_bought": -500000 
}

# DISCOUNT CHEQUES
CHEQUE_COST = 500000 
NEXT_CHEQUE_THRESHOLD = 100_000_000 
MAX_DISCOUNT = 50 

# ────────────────────────────── THEME & UI ──────────────────────────────
THEMES = {
    "Light": {"bg": "#FFFFFF", "text": "#000000", "primary": "#009E60", "card": "#F0F2F6"},
    "Dark": {"bg": "#1E1E1E", "text": "#FFFFFF", "primary": "#FFD700", "card": "#2D2D2D"},
    "Kenya": {"bg": "#FFFFFF", "text": "#000000", "primary": "#009E60", "card": "#FFD700"},
    "Ocean": {"bg": "#E3F2FD", "text": "#0D47A1", "primary": "#1E88E5", "card": "#BBDEFB"}
}

FONTS = ["Inter", "Roboto", "Open Sans", "Lato", "Montserrat", "Poppins", "Nunito", "Raleway"]
FONT_SIZES = ["Small", "Medium", "Large", "Extra Large"]

def apply_theme():
    theme = st.session_state.get("theme", "Kenya")
    font = st.session_state.get("font", "Inter")
    size = st.session_state.get("font_size", "Medium")
    size_map = {"Small": "12px", "Medium": "14px", "Large": "16px", "Extra Large": "18px"}
    t = THEMES[theme]
    st.markdown(f"""
    <style>
        .reportview-container {{ background: {t['bg']}; color: {t['text']}; }}
        .sidebar .sidebar-content {{ background: {t['card']}; }}
        .stButton>button {{ background: {t['primary']}; color: white; border-radius: 8px; }}
        .stTextInput>div>input, .stSelectbox>div>select {{ border: 1px solid {t['primary']}; }}
        h1, h2, h3, h4 {{ color: {t['primary']}; }}
        body {{ font-family: '{font}', sans-serif; font-size: {size_map[size]}; }}
        .xp-bar {{ background: linear-gradient(90deg, {t['primary']} 0%, #FFD700 100%); height: 10px; border-radius: 5px; }}
        .badge {{ display: inline-block; background: {t['primary']}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 0.8rem; margin: 2px; }}
    </style>
    """, unsafe_allow_html=True)

# ────────────────────────────── MUST BE FIRST ──────────────────────────────
st.set_page_config(page_title="PrepKe AI: Your Kenyan AI Tutor", page_icon="KE", layout="wide", initial_sidebar_state="expanded")

# INIT
try:
    db = Database()
    # Dummy AIEngine for demonstration, assuming user has their implementation
    class AIEngine:
        def __init__(self, key): pass
        def generate_response(self, prompt, system_instruction): return f"AI response for: {prompt[:50]}..."
        def generate_exam_questions(self, subject, exam_type, num_questions, topic):
            return [{"question": f"Q{i+1} on {subject}/{topic}", "options": ["A) Opt1", "B) Opt2", "C) Opt3", "D) Opt4"], "answer": "A) Opt1", "feedback": "Good luck!"} for i in range(num_questions)]
        def grade_mcq(self, questions, user_answers):
             correct = sum(1 for i, q in enumerate(questions) if user_answers.get(i) and user_answers.get(i).startswith(q['answer'][0]))
             total = len(questions)
             percentage = int((correct / total) * 100) if total > 0 else 0
             results = [{"question": q["question"], "user_answer": user_answers.get(i, "N/A"), "correct_answer": q["answer"], "is_correct": user_answers.get(i) and user_answers.get(i).startswith(q['answer'][0]), "feedback": q["feedback"]} for i, q in enumerate(questions)]
             return {"correct": correct, "total": total, "percentage": percentage, "results": results}
        def grade_essay(self, essay, rubric): return {"score": 75, "feedback": "Excellent structure and content."}
             
    ai_engine = AIEngine(st.secrets.get("GEMINI_API_KEY", ""))
except Exception as e:
    st.error(f"INIT FAILED: {e}")
    st.stop()

# SESSION STATE
def init_session():
    defaults = {
        "logged_in": False, "user_id": None, "is_admin": False, "user": None,
        "show_welcome": True, "chat_history": [], "current_subject": "Mathematics",
        "pdf_text": "", "current_tab": "Chat Tutor", "theme": "Kenya", "font": "Inter", "font_size": "Medium",
        "exam_questions": None, "user_answers": {}, "exam_submitted": False,
        "pdf_chat_history": [],
        "show_qr": False, # 2FA state
        "secret_key": None, # 2FA state
        "qr_code": None, # 2FA state (bytes)
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# USER TIER
def get_user_tier():
    if not st.session_state.logged_in: return "basic"
    user = db.get_user(st.session_state.user_id)
    if not user: return "basic"
    
    st.session_state.user = user 
    if user.get("role") == "admin":
        st.session_state.is_admin = True
        return "admin"
        
    if user.get("is_premium") and db.check_premium_validity(user["user_id"]):
        return "premium"
    return "basic"


def enforce_access():
    if not st.session_state.logged_in: return
    tier = get_user_tier()
    tab = st.session_state.current_tab
    
    db.update_user_activity(st.session_state.user_id)
    
    # Check streak only once on app load
    if 'streak_checked' not in st.session_state:
        db.update_streak(st.session_state.user_id)
        st.session_state.streak_checked = True 

    if tier == "admin": return

    if tier == "basic":
        if tab in ["PDF Q&A", "Exam Prep", "Essay Grader"]:
            st.warning("Upgrade to **Premium** to access this feature.")

        if tab == "Chat Tutor" and db.get_daily_question_count(st.session_state.user_id) >= 10:
            st.error("You've used your **10 free questions** today. Upgrade to Premium!")
        if tab == "PDF Q&A" and db.get_daily_pdf_count(st.session_state.user_id) >= 3:
            st.error("You've used your **3 free PDF uploads** today. Upgrade to Premium!")


# GAMIFICATION
@st.cache_data(ttl=600) 
def get_user_level(user_data):
    total_xp = user_data.get("total_xp", 0)
    spendable_xp = user_data.get("spendable_xp", total_xp)
    tier = get_user_tier()
    max_level = float('inf') if tier != "basic" else BASIC_MAX_LEVEL

    level = 1
    for lvl, req in LEVELS.items():
        if total_xp >= req and lvl <= max_level:
            level = lvl
    prev_req = LEVELS.get(level - 1, 0)
    current = total_xp - prev_req
    next_req = LEVELS.get(level + 1, float('inf')) - prev_req
    return level, current, next_req, spendable_xp

def award_xp(user_id, points, reason):
    db.add_xp(user_id, points)
    st.toast(f"**+{points} XP** – {reason} 🎉")

def buy_discount_cheque(user_id):
    user = db.get_user(user_id)
    spendable = user.get("spendable_xp", 0)
    total_xp = user.get("total_xp", 0)
    if spendable < CHEQUE_COST:
        st.error("Not enough spendable XP!")
        return
    if total_xp < NEXT_CHEQUE_THRESHOLD:
        st.error(f"Need {NEXT_CHEQUE_THRESHOLD:,} total XP to unlock next cheque!")
        return
    db.add_xp(user_id, -CHEQUE_COST, spendable=True)
    db.increase_discount(user_id, 5)
    db.reset_spendable_progress(user_id)
    st.success("**5% Discount Cheque Bought!** Premium now 5% off! 💰")

# UI (sidebar/login/welcome are unchanged)
def welcome_screen():
    st.markdown("""
    <div style="background:linear-gradient(135deg,#009E60,#FFD700);padding:80px;border-radius:20px;text-align:center;color:white">
        <h1>PrepKe AI</h1>
        <p style="font-size:1.3rem">Your Kenyan AI Tutor • KCPE • KPSEA • KJSEA • KCSE</p>
        <p style="font-size:1.1rem">Earn XP • Level Up • Unlock Badges • Compete Nationally</p>
    </div>
    """, unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("Start Learning!", type="primary", use_container_width=True):
            st.session_state.show_welcome = False
            # st.rerun() # Removed for warning fix

def login_block():
    if st.session_state.logged_in: return

    st.markdown("### Login / Sign Up")
    choice = st.radio("Action", ["Login", "Sign Up"], horizontal=True, label_visibility="collapsed")
    
    email = st.text_input("Email", key=f"{choice.lower()}_email")
    pwd = st.text_input("Password", type="password", key=f"{choice.lower()}_pwd")
    
    totp = ""
    if choice == "Login":
        user_check = db.get_user_by_email(email)
        if user_check and db.is_2fa_enabled(user_check["user_id"]):
            totp = st.text_input("2FA Code", key="totp")

    if st.button(choice, type="primary"):
        if choice == "Sign Up":
            if len(pwd) < 6: st.error("Password ≥6 chars."); return
            uid = db.create_user(email, pwd)
            if uid:
                db.add_xp(uid, 50)
                st.success("Account created! +50 XP 🥳")
            else:
                st.error("Email exists.")
            return

        # Login Logic
        user = db.get_user_by_email(email)
        if not user: st.error("Invalid email/password."); return

        stored_hash = user["password_hash"]
        if isinstance(stored_hash, str): stored_hash = stored_hash.encode()
        if not bcrypt.checkpw(pwd.encode(), stored_hash): st.error("Invalid email/password."); return

        if db.is_2fa_enabled(user["user_id"]) and not db.verify_2fa_code(user["user_id"], totp):
            st.error("Invalid 2FA code.")
            return

        db.update_user_activity(user["user_id"])
        st.session_state.update({
            "logged_in": True, "user_id": user["user_id"], "is_admin": user["role"] == "admin", "user": user
        })
        award_xp(user["user_id"], 20, "Daily login")
        # st.rerun() # Removed for warning fix

def sidebar():
    with st.sidebar:
        apply_theme()
        st.markdown("## PrepKe AI 🇰🇪")
        tier = get_user_tier()
        st.markdown(f"**Tier:** `{tier.upper()}`")

        user = db.get_user(st.session_state.user_id) 
        st.session_state.user = user 
        level, current, next_xp, spendable = get_user_level(user)
        st.markdown(f"### Level {level} {'(Max)' if tier == 'basic' and level == BASIC_MAX_LEVEL else ''}")
        
        if next_xp != float('inf'):
            progress_percent = min(current/next_xp*100, 100)
            st.markdown(f"<div class='xp-bar' style='width: {progress_percent}%'></div>", unsafe_allow_html=True)
            st.caption(f"**{current:,}/{next_xp:,} XP** to next level")
        else:
            st.success(f"Max Level Reached! XP: {current:,}")


        st.markdown(f"**Spendable XP:** {spendable:,}")
        if st.session_state.logged_in and spendable >= CHEQUE_COST and user.get("total_xp", 0) >= NEXT_CHEQUE_THRESHOLD:
            if st.button("Buy 5% Discount Cheque"):
                buy_discount_cheque(st.session_state.user_id)

        streak = db.get_user(st.session_state.user_id).get("streak", 0) # Use the updated streak from the DB
        st.markdown(f"**Streak:** {streak} days 🔥")

        st.session_state.current_subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))

        badges = json.loads(user.get("badges", "[]"))
        if badges:
            st.markdown("### Badges 🥇")
            for b in badges[:6]:
                st.markdown(f"<span class='badge'>{BADGES.get(b, b)}</span>", unsafe_allow_html=True)

        st.markdown("### National Leaderboard 🌍")
        lb = db.get_xp_leaderboard()[:5]
        
        for i, e in enumerate(lb):
            st.markdown(f"**{i+1}.** {e['email']} ({e['total_xp']:,} XP)")
        
        if st.button("Log Out 👋", type="secondary", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_id = None
            st.session_state.is_admin = False
            # st.rerun() # Removed for warning fix

# --------------------------------------------------------------------------------
# 1. CHAT TUTOR
# --------------------------------------------------------------------------------
def chat_tab():
    st.session_state.current_tab = "Chat Tutor"
    st.header(f"Chat Tutor: {st.session_state.current_subject}")
    
    enforce_access()

    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input(f"Ask about {st.session_state.current_subject}...", key="chat_input"):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
            
        with st.chat_message("assistant"):
            with st.spinner("PrepKe AI is thinking..."):
                system_prompt = get_enhanced_prompt(st.session_state.current_subject, prompt)
                response = ai_engine.generate_response(prompt, system_prompt)
                st.markdown(response)

        st.session_state.chat_history.append({"role": "assistant", "content": response})
        db.add_chat_history(st.session_state.user_id, st.session_state.current_subject, prompt, response)
        award_xp(st.session_state.user_id, XP_RULES["question_asked"], "Chat question")
        # st.rerun() is handled by chat_input submission

# --------------------------------------------------------------------------------
# 2. PROGRESS (XP Bar is here)
# --------------------------------------------------------------------------------
def progress_tab():
    st.session_state.current_tab = "Progress"
    user_id = st.session_state.user_id
    st.header("Your Learning Progress 📊")

    all_scores = db.get_user_scores(user_id)
    leaderboard = db.get_xp_leaderboard()

    # 1. XP & Level 
    user = db.get_user(user_id)
    level, current, next_xp, spendable = get_user_level(user)
    st.subheader("XP and Level Status")
    st.info(f"You are currently at **Level {level}** with **{user.get('total_xp', 0):,} Total XP**.")

    st.markdown("#### Progress to Next Level")
    if next_xp != float('inf'):
        progress_percent = min(current/next_xp*100, 100)
        st.markdown(f"<p style='font-size:1rem; margin-bottom: 0;'>**{current:,} / {next_xp:,} XP**</p>", unsafe_allow_html=True)
        st.progress(progress_percent / 100) 
        
    else:
        st.success(f"Max Level Reached! XP: {current:,}")
    
    st.divider()
    
    # 2. Score History 
    st.subheader("Exam and Essay Score History")

    if all_scores:
        scores_df = pd.DataFrame(all_scores)
        scores_df['timestamp'] = pd.to_datetime(scores_df['timestamp'])
        
        exam_data = scores_df[scores_df['category'] == 'exam'].copy()
        if not exam_data.empty:
            st.markdown("#### Practice Exam Score Trend")
            fig = px.line(exam_data, x='timestamp', y='score', markers=True, title='Practice Exam Scores Over Time')
            st.plotly_chart(fig, use_container_width=True)
            with st.expander("Recent Practice Exam Records"):
                st.dataframe(exam_data[['timestamp', 'score']].rename(columns={'timestamp': 'Date Taken', 'score': 'Exam Score (%)'}), use_container_width=True, hide_index=True)
        else:
            st.info("No practice exam scores recorded yet.")

    else:
        st.info("Start taking exams and grading essays to track your progress!")
        
    st.divider()
    
    # 3. Leaderboard 
    st.subheader("Global XP Leaderboard (Top 10)")
    if leaderboard:
        lb_df = pd.DataFrame(leaderboard).rename(columns={'email': 'User Email', 'total_xp': 'Total Experience Points (XP)', 'rank': 'Rank'})
        st.dataframe(lb_df, use_container_width=True, hide_index=True)
    else:
        st.info("Leaderboard is empty.")

# --------------------------------------------------------------------------------
# 3. SETTINGS (2FA FIX APPLIED)
# --------------------------------------------------------------------------------
def settings_tab():
    st.session_state.current_tab = "Settings"
    st.header("Settings & Profile ⚙️")
    user_id = st.session_state.user_id
    
    # --- Appearance Settings ---
    st.markdown("### Appearance")
    col1, col2 = st.columns(2)
    with col1:
        st.selectbox("Theme", list(THEMES.keys()), key="theme", on_change=st.rerun) 
    with col2:
        st.selectbox("Font", FONTS, key="font", on_change=st.rerun)
    
    st.selectbox("Font Size", FONT_SIZES, key="font_size", on_change=st.rerun)

    # --- 2FA Settings (FIXED LOGIC AND RERUN) ---
    st.markdown("### Two-Factor Authentication (2FA)")
    
    if db.is_2fa_enabled(user_id):
        st.success("2FA is **Enabled** ✅")
        if st.button("Disable 2FA", key="disable_2fa_btn"):
            db.disable_2fa(user_id)
            st.session_state.show_qr = False 
            st.success("2FA Disabled. Rerunning...")
            # st.rerun() removed (relying on button rerun)
    else:
        st.info("2FA is **Disabled**. Enhance your security.")
        
        if st.session_state.get("show_qr"):
            st.warning("Please scan the QR code and verify before closing this tab.")
            
            # Display QR code image from stored bytes
            qr_bytes = st.session_state.get("qr_code")
            if qr_bytes:
                # Convert bytes to base64 string for embedding
                b64_qr = base64.b64encode(qr_bytes).decode()
                st.markdown(
                    f'<img src="data:image/png;base64,{b64_qr}" style="width:200px;">',
                    unsafe_allow_html=True
                )
            
            st.code(st.session_state.get("secret_key"))
            
            verification_code = st.text_input("Enter 6-digit Code to Verify", max_chars=6, key="2fa_verify_code")
            
            if st.button("Confirm 2FA Setup", type="primary"):
                if db.verify_2fa_code(user_id, verification_code):
                    award_xp(user_id, XP_RULES["2fa_enabled"], "2FA Enabled")
                    st.session_state.show_qr = False
                    st.session_state.secret_key = None
                    st.session_state.qr_code = None
                    st.success("2FA successfully enabled!")
                    # st.rerun() removed
                else:
                    st.error("Invalid 2FA code. Please try again.")

        else:
            if st.button("Enable 2FA", key="enable_2fa_btn"):
                # FIX: Use db.enable_2fa() which uses the correct user_2fa table
                secret, qr_bytes = db.enable_2fa(user_id)
                
                st.session_state.show_qr = True
                st.session_state.secret_key = secret
                st.session_state.qr_code = qr_bytes 
                # st.rerun() removed (relying on button rerun)

    # --- Profile Settings ---
    st.markdown("### Profile")
    current_user_data = db.get_user(user_id) 
    current_name = current_user_data.get("name", "")
    
    new_name = st.text_input("Name", current_name)
    
    if st.button("Save Profile", type="primary"):
        if new_name != current_name:
            db.update_profile(user_id, new_name)
            award_xp(user_id, XP_RULES["profile_complete"], "Profile completed")
            st.success("Profile updated successfully!")
            # st.rerun() removed
        else:
            st.info("Name is already saved.")

# --------------------------------------------------------------------------------
# 4. PDF Q&A
# --------------------------------------------------------------------------------
def pdf_tab():
    st.session_state.current_tab = "PDF Q&A"
    enforce_access()
    st.header(f"PDF Q&A: Analyze Your Documents 📄")
    
    uploaded_file = st.file_uploader("Upload a PDF to analyze", type="pdf")
    
    if uploaded_file:
        file_bytes = uploaded_file.read()
        filename = uploaded_file.name
        
        st.session_state.pdf_text = cached_pdf_extract(file_bytes, filename)
        
        if st.session_state.pdf_text.startswith("Error"):
            st.error(st.session_state.pdf_text)
            st.session_state.pdf_text = ""
            st.session_state.pdf_chat_history = []
            return
            
        st.success(f"Successfully loaded '{filename}'. Context length: {len(st.session_state.pdf_text):,} characters.")
        
        if st.checkbox("Show Extracted Text Summary", key="pdf_summary_check"):
            st.code(st.session_state.pdf_text[:1000] + "...") 

        if 'pdf_chat_history' not in st.session_state:
            st.session_state.pdf_chat_history = []
            
        for message in st.session_state.pdf_chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        pdf_prompt = st.chat_input("Ask a question about the PDF...", key="pdf_chat_input")
        
        if pdf_prompt:
            st.session_state.pdf_chat_history.append({"role": "user", "content": pdf_prompt})
            with st.chat_message("user"):
                st.markdown(pdf_prompt)
                
            with st.chat_message("assistant"):
                with st.spinner("Analyzing document..."):
                    context = st.session_state.pdf_text
                    truncated_context = context[:10000] 
                    
                    system_prompt = get_enhanced_prompt(
                        st.session_state.current_subject, 
                        pdf_prompt, 
                        context=f"Document Snippet: {truncated_context}"
                    )
                    
                    response = ai_engine.generate_response(
                        pdf_prompt, 
                        system_prompt
                    )
                    st.markdown(response)

            st.session_state.pdf_chat_history.append({"role": "assistant", "content": response})
            
            award_xp(st.session_state.user_id, XP_RULES["pdf_question"], "PDF Question")
            db.increment_daily_pdf(st.session_state.user_id)
            # st.rerun() is handled by chat_input submission

    else:
        st.info("Upload a PDF file (e.g., class notes, past paper) to start Q&A.")
        if st.session_state.pdf_text:
            st.session_state.pdf_text = "" 
            st.session_state.pdf_chat_history = []

# --------------------------------------------------------------------------------
# 5. EXAM PREP (Fixed: 100 Qs, Topic Select, XP Fix)
# --------------------------------------------------------------------------------
def exam_tab():
    st.session_state.current_tab = "Exam Prep"
    enforce_access()
    st.header("Exam Prep: Generate & Take Quizzes 📝")

    col1, col2, col3, col4 = st.columns([2, 1, 1, 2])
    
    # 1. Controls
    kcse_subjects = EXAM_TYPES.get("KCSE", {}).get("subjects", ["Mathematics"])
    exam_focus_types = list(EXAM_TYPES.keys())

    with col1:
        selected_subject = st.selectbox(
            "Select Subject", 
            kcse_subjects, 
            key="exam_subject",
            index=kcse_subjects.index(st.session_state.current_subject) if st.session_state.current_subject in kcse_subjects else 0
        )
    with col2:
        num_questions = st.slider("No. of Questions", 5, 100, 5) 
    with col3:
        exam_type = st.selectbox("Exam Focus", exam_focus_types)
    with col4:
        selected_topic = st.text_input("Specific Topic (Optional)", placeholder="e.g., Quadratic Equations, Inheritance")

    if st.session_state.exam_questions is None or st.session_state.exam_questions[0].get("subject") != selected_subject:
        if st.button(f"Generate {num_questions} Questions for {selected_subject}", type="primary"):
            st.session_state.user_answers = {}
            st.session_state.exam_submitted = False
            
            with st.spinner(f"Generating {exam_type}-style questions for {selected_subject}..."):
                questions = ai_engine.generate_exam_questions(selected_subject, exam_type, num_questions, selected_topic)
                
                for q in questions: 
                    q["subject"] = selected_subject
                    q["topic"] = selected_topic 
                    
                st.session_state.exam_questions = questions
                
                # XP FIX: Award minimal XP for generation start once
                award_xp(st.session_state.user_id, XP_RULES["quiz_generated"], "Quiz Generation Start") 
                # st.rerun() removed

    # 2. Display Quiz
    if st.session_state.exam_questions:
        st.subheader(f"{selected_subject} Quiz ({len(st.session_state.exam_questions)} Questions)")
        
        quiz_form = st.form(key="quiz_form")
        
        for i, q in enumerate(st.session_state.exam_questions):
            key = f"q_{i}"
            options_text = q.get("options", [])
            
            options_display = options_text
            
            default_index = 0
            current_answer_text = st.session_state.user_answers.get(i)
            if current_answer_text and current_answer_text in options_display:
                default_index = options_display.index(current_answer_text)

            quiz_form.markdown(f"**{i+1}.** {q['question']}")
            selected_option_text = quiz_form.radio(
                "Select your answer:",
                options=options_display,
                index=default_index,
                key=key,
                disabled=st.session_state.exam_submitted
            )
            st.session_state.user_answers[i] = selected_option_text
            quiz_form.markdown("---")

        submit_col, reset_col, _ = quiz_form.columns([1, 1, 4])
        
        if not st.session_state.exam_submitted:
            if submit_col.form_submit_button("Submit Exam", type="primary"):
                st.session_state.exam_submitted = True
                # st.rerun() removed (handled by form submit)
        else:
            submit_col.form_submit_button("Submitted", disabled=True)
            
        if reset_col.form_submit_button("New Quiz", type="secondary"):
            st.session_state.exam_questions = None
            st.session_state.user_answers = {}
            st.session_state.exam_submitted = False
            # st.rerun() removed (handled by form submit)

    # 3. Display Results
    if st.session_state.exam_submitted:
        results = ai_engine.grade_mcq(st.session_state.exam_questions, st.session_state.user_answers)
        percentage = results["percentage"]
        
        st.subheader(f"Exam Results: {percentage}%")
        st.info(f"You answered **{results['correct']}** out of **{results['total']}** questions correctly.")
        
        # XP Award Logic
        xp_earned = int(percentage // 10) * XP_RULES["exam_10_percent"]
        if percentage == 100:
             xp_earned += XP_RULES["perfect_score"]
             db.add_badge(st.session_state.user_id, "perfect_score")
             st.balloons()
        award_xp(st.session_state.user_id, xp_earned, f"Exam score {percentage}%")
        
        db.add_score(st.session_state.user_id, 'exam', percentage) # FIX: Use add_score

        with st.expander("Detailed Feedback"):
            for i, result in enumerate(results["results"]):
                icon = "✅" if result["is_correct"] else "❌"
                st.markdown(f"**{i+1}.** {result['question']}")
                st.markdown(f"**Your Answer:** {result['user_answer']} {icon}")
                st.markdown(f"**Correct Answer:** {result['correct_answer']}")
                st.markdown(f"**Feedback:** *{result['feedback']}*")
                st.divider()


# --------------------------------------------------------------------------------
# 6. ESSAY GRADER 
# --------------------------------------------------------------------------------
def essay_tab():
    st.session_state.current_tab = "Essay Grader"
    enforce_access()
    st.header("Essay Grader: Get KCSE/KPSEA Feedback ✍️")
    
    st.warning("This feature costs a small amount of XP to use due to high AI computation.")
    
    essay_title = st.text_input("Essay Title/Topic", key="essay_title", value=f"An Essay on {st.session_state.current_subject}")
    essay_text = st.text_area("Paste your Essay here (min 100 words)", height=300, key="essay_text")
    
    default_rubric = f"""
    Grade this {st.session_state.current_subject} essay based on:
    1. Content/Relevance (40%): How well the essay answers the prompt and uses relevant Kenyan examples.
    2. Structure/Flow (30%): Organization, use of paragraphs, topic sentences, and logical progression.
    3. Language/Grammar (30%): Accuracy of English/Kiswahili (as appropriate), spelling, and vocabulary.
    """
    
    rubric = st.text_area("Custom Grading Rubric (Optional)", default_rubric, height=150)

    if st.button("Grade Essay", type="primary"):
        if len(essay_text.split()) < 100:
            st.error("Essay must be at least 100 words for grading.")
            return

        xp_cost = 50 
        user = db.get_user(st.session_state.user_id)
        if user.get("spendable_xp", 0) < xp_cost:
            st.error(f"You need {xp_cost} spendable XP to use the Essay Grader. Current: {user.get('spendable_xp', 0)}")
            return
            
        db.add_xp(st.session_state.user_id, -xp_cost, spendable=True)
        st.toast(f"Deducted {xp_cost} spendable XP for grading.")

        with st.spinner("Analyzing and Grading Essay..."):
            try:
                grading_result = ai_engine.grade_essay(essay_text, rubric)
                
                score = grading_result.get("score", 0)
                feedback = grading_result.get("feedback", "No detailed feedback received.")
                
                if isinstance(score, str) and score.isdigit():
                    score = int(score)
                elif not isinstance(score, int):
                    score = 0
                
                st.success(f"Final Score: **{score}%**")
                
                xp_earned = int(score // 5) * XP_RULES["essay_5_percent"]
                award_xp(st.session_state.user_id, xp_earned, f"Essay Graded: {score}%")
                
                db.add_score(st.session_state.user_id, 'essay', score) # FIX: Use add_score

                st.markdown("### Detailed Feedback")
                st.markdown(feedback)
                
            except Exception as e:
                st.error(f"An error occurred during grading: {e}")
                
    st.caption("Grading relies on the AI model using the provided rubric and Kenyan curriculum standards.")

# --------------------------------------------------------------------------------
# 7. PREMIUM UPGRADE (Unchanged placeholder)
# --------------------------------------------------------------------------------
def premium_tab(): st.info("Premium Upgrade content goes here...")


# --------------------------------------------------------------------------------
# 8. ADMIN DASHBOARD
# --------------------------------------------------------------------------------
def admin_dashboard():
    st.session_state.current_tab = "Admin"
    st.title("👑 Admin Dashboard")
    
    # 1. User Management
    st.header("1. User Management")
    all_users = db.get_all_users()
    
    users_data = []
    for user in all_users:
        if user['user_id'] == st.session_state.user_id: continue 
        
        tier = "Premium" if user['is_premium'] and db.check_premium_validity(user['user_id']) else "Basic"
        tier = "Admin" if user['role'] == 'admin' else tier
        status = "Banned 🚫" if user['is_banned'] else "Active ✅"
        
        users_data.append({
            "ID": user['user_id'],
            "Email": user['email'],
            "Role": tier,
            "XP": user['total_xp'],
            "Status": status
        })
    
    st.markdown("### All Users")
    
    if users_data:
        
        # Display header
        col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([1, 2, 1.5, 1, 1, 1, 1, 1])
        col1.markdown("**ID**")
        col2.markdown("**Email**")
        col3.markdown("**Role**")
        col4.markdown("**XP**")
        col5.markdown("**Status**")
        col6.markdown("**Ban/Unban**")
        col7.markdown("**Tier**")
        col8.markdown("**Reset**")
        st.markdown("---")
        
        # Display table with controls
        for user_row in users_data:
            col1, col2, col3, col4, col5, col6, col7, col8 = st.columns([1, 2, 1.5, 1, 1, 1, 1, 1])
            
            user_id = user_row["ID"]
            
            col1.write(user_row["ID"])
            col2.write(user_row["Email"])
            col3.write(user_row["Role"])
            col4.write(f"{user_row['XP']:,}")
            col5.write(user_row["Status"])
            
            # Ban/Unban Button
            if user_row["Status"] == "Active ✅":
                if col6.button("Ban 🚫", key=f"ban_{user_id}", type="secondary", help="Ban user access"):
                    db.ban_user(user_id)
                    st.toast(f"User {user_id} banned.")
                    # st.rerun() removed
            else:
                if col6.button("Unban ✅", key=f"unban_{user_id}", type="primary", help="Restore user access"):
                    db.unban_user(user_id) 
                    st.toast(f"User {user_id} unbanned.")
                    # st.rerun() removed
            
            # Premium Upgrade/Downgrade Button
            if user_row["Role"] in ["Basic", "Admin"]:
                if col7.button("Upgrade ⭐", key=f"upgrade_{user_id}", type="primary", help="Set user to Premium for 30 days"):
                    db.upgrade_to_premium(user_id)
                    st.toast(f"User {user_id} upgraded to Premium.")
                    # st.rerun() removed
            else: # Premium
                if col7.button("Downgrade ⬇️", key=f"downgrade_{user_id}", type="secondary", help="Remove Premium status"):
                    db.downgrade_to_basic(user_id)
                    st.toast(f"User {user_id} downgraded to Basic.")
                    # st.rerun() removed
            
            # Reset XP
            if col8.button("Reset XP 🔄", key=f"reset_xp_{user_id}", help="Clear all XP, badges, and discounts"):
                db.conn.execute("UPDATE users SET total_xp = 0, spendable_xp = 0, discount = 0, badges = '[]', streak = 0 WHERE user_id = ?", (user_id,))
                db.conn.commit()
                st.toast(f"XP/Gamification reset for user {user_id}.")
                # st.rerun() removed

        st.divider()

    else:
        st.info("No other users found.")

    # 2. Pending Payments 
    st.header("2. Pending Premium Payments")
    
    pending_payments = db.get_pending_payments()
    
    if pending_payments:
        for payment in pending_payments:
            user = db.get_user(payment['user_id'])
            user_label = user.get('email') if user else f"User {payment.get('user_id', 'Unknown')}"

            with st.expander(f"**{user_label}** - Code: {payment.get('mpesa_code', 'N/A')}"):
                st.markdown(f"**Phone:** {payment.get('phone', 'N/A')} - **Submitted:** {payment.get('timestamp', 'N/A')}")
                col_a, col_r, _ = st.columns([1, 1, 4])
                with col_a:
                    if st.button("✅ Approve", key=f"approve_{payment['id']}"):
                        db.approve_manual_payment(payment['id']) 
                        st.toast(f"Approved Premium for {user_label}.")
                        # st.rerun() removed
                with col_r:
                    if st.button("❌ Reject", key=f"reject_{payment['id']}"):
                        db.reject_manual_payment(payment['id']) 
                        st.toast(f"Rejected payment for {user_label}.")
                        # st.rerun() removed
        st.divider()
    else:
        st.info("No pending payments to review.")

# MAIN
def main():
    try:
        init_session()
        apply_theme()
        if st.session_state.show_welcome: welcome_screen(); return
        login_block()
        if not st.session_state.logged_in: st.info("Log in to start learning! 📖"); return
        sidebar()
        
        tabs = ["Chat Tutor", "Progress", "Settings"]
        tier = get_user_tier()
        
        if tier in ["premium", "admin"]:
            tabs += ["PDF Q&A", "Exam Prep", "Essay Grader"]
        if tier == "basic":
            tabs.append("Premium")
        if st.session_state.is_admin:
            tabs.append("Admin")

        tab_objs = st.tabs(tabs)
        tab_map = {
            "Chat Tutor": chat_tab, "Progress": progress_tab, "Settings": settings_tab,
            "PDF Q&A": pdf_tab, "Exam Prep": exam_tab, "Essay Grader": essay_tab,
            "Premium": premium_tab, "Admin": admin_dashboard
        }
        for name, obj in zip(tabs, tab_objs):
            with obj:
                st.session_state.current_tab = name 
                tab_map[name]()
    except Exception as e:
        st.error(f"CRASH: {e}")

if __name__ == "__main__":
    main()
