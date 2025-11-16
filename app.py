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
import io # Added for PDF Q&A

# ==============================================================================
# GAMIFICATION: LEVELS + XP SYSTEM
# ==============================================================================
LEVELS = {
    1: 0, 2: 100, 3: 250, 4: 500, 5: 1000,
    6: 2000, 7: 3500, 8: 6000, 9: 10000, 10: 15000,
    11: 25000, 12: 40000, 13: 60000, 14: 90000, 15: 130000
}

BASIC_MAX_LEVEL = 5  # Basic users can't go beyond Level 5

# XP EARNING RULES (Education-Focused)
XP_RULES = {
    "question_asked": 10,
    "pdf_upload": 30,
    "pdf_question": 15,
    "exam_10_percent": 1,  # 1 XP per 10% score
    "essay_5_percent": 1,  # 1 XP per 5% score
    "perfect_score": 100,
    "daily_streak": 20,
    "first_login": 50,
    "2fa_enabled": 20,
    "profile_complete": 30,
    "badge_earned": 50,
    "leaderboard_top3": 200,
    "discount_cheque_bought": -500000  # Costs 500K spendable XP
}

# DISCOUNT CHEQUES
CHEQUE_COST = 500000  # XP to buy 5% discount
NEXT_CHEQUE_THRESHOLD = 100_000_000  # 100M XP to unlock next purchase
MAX_DISCOUNT = 50  # Max 50% discount

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
# 🏆 App Name Change: PrepKe AI 🇰🇪
st.set_page_config(page_title="PrepKe AI: Your Kenyan AI Tutor", page_icon="KE", layout="wide", initial_sidebar_state="expanded")

# INIT
try:
    db = Database()
    ai_engine = AIEngine(st.secrets.get("GEMINI_API_KEY", ""))
except Exception as e:
    st.error(f"INIT FAILED: {e}")
    st.stop()

# SESSION STATE
def init_session():
    defaults = {
        "logged_in": False, "user_id": None, "is_admin": False, "user": None,
        "show_welcome": True, "chat_history": [], "current_subject": "Mathematics",
        "pdf_text": "", "pdf_filename": "", "pdf_chat_history": [], # Added for PDF tab
        "current_tab": "Chat Tutor", "theme": "Kenya", "font": "Inter", "font_size": "Medium",
        "exam_questions": None, "user_answers": {}, "exam_submitted": False
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# USER TIER
def get_user_tier():
    if st.session_state.is_admin: return "admin"
    user = db.get_user(st.session_state.user_id)
    if not user: return "basic"
    if user.get("is_premium") and db.check_premium_validity(st.session_state.user_id):
        return "premium"
    return "basic"

def enforce_access():
    tier = get_user_tier()
    tab = st.session_state.current_tab
    if tier == "admin": return
    if tier == "basic" and tab not in ["Chat Tutor", "Progress", "Settings", "Premium"]:
        st.warning("Upgrade to **Premium** to access this feature.")
        st.stop()
    if tier == "basic":
        if tab == "Chat Tutor" and db.get_daily_question_count(st.session_state.user_id) >= 10:
            st.error("You've used your **10 questions** today. Upgrade to Premium!")
            st.stop()
        if tab == "PDF Q&A" and db.get_daily_pdf_count(st.session_state.user_id) >= 3:
            st.error("You've used your **3 PDF uploads** today. Upgrade to Premium!")
            st.stop()

# GAMIFICATION
# FIX 1: Removed @st.cache_data(ttl=600) for instant XP synchronization
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

# UI
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
            st.rerun()

def login_block():
    if st.session_state.logged_in: return

    st.markdown("### Login / Sign Up")
    choice = st.radio("Action", ["Login", "Sign Up", "Forgot Password"], horizontal=True, label_visibility="collapsed")
    
    if choice == "Forgot Password":
        email = st.text_input("Email")
        if st.button("Send Reset Code"):
            user = db.get_user_by_email(email)
            if user and db.is_2fa_enabled(user["user_id"]):
                code = db.generate_otp(user["user_id"])
                st.success("2FA code sent to your authenticator!")
                st.session_state.reset_user_id = user["user_id"]
                st.session_state.reset_step = 1
            else:
                st.error("No 2FA-enabled account.")
        if st.session_state.get("reset_step") == 1:
            code = st.text_input("2FA Code")
            if st.button("Verify"):
                if db.verify_2fa_code(st.session_state.reset_user_id, code):
                    st.session_state.reset_step = 2
                else:
                    st.error("Invalid code.")
        if st.session_state.get("reset_step") == 2:
            new_pwd = st.text_input("New Password", type="password")
            confirm = st.text_input("Confirm", type="password")
            if st.button("Reset"):
                if new_pwd == confirm and len(new_pwd) >= 6:
                    db.update_password(st.session_state.reset_user_id, new_pwd)
                    st.success("Password reset! Log in.")
                    st.session_state.reset_step = 0
                    st.rerun()
                else:
                    st.error("Passwords must match and be ≥6 chars.")
        return

    email = st.text_input("Email", key=f"{choice.lower()}_email")
    pwd = st.text_input("Password", type="password", key=f"{choice.lower()}_pwd")
    totp = st.text_input("2FA Code", key="totp") if choice == "Login" else ""

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
        award_xp(user["user_id"], XP_RULES["daily_streak"], "Daily login") # Using XP_RULES
        st.rerun()

def sidebar():
    with st.sidebar:
        apply_theme()
        st.markdown("## PrepKe AI 🇰🇪")
        tier = get_user_tier()
        st.markdown(f"**Tier:** `{tier.upper()}`")

        user = db.get_user(st.session_state.user_id) # Refresh user data for accurate XP
        st.session_state.user = user # Update session state
        level, current, next_xp, spendable = get_user_level(user)
        st.markdown(f"### Level {level} {'(Max)' if tier == 'basic' and level == BASIC_MAX_LEVEL else ''}")
        
        # Avoid division by zero if next_req is inf (max level)
        if next_xp != float('inf'):
            progress_percent = current/next_xp*100
            st.markdown(f"<div class='xp-bar' style='width: {progress_percent}%'></div>", unsafe_allow_html=True)
            st.caption(f"**{current:,}/{next_xp:,} XP** to next level")
        else:
            st.success(f"Max Level Reached! XP: {current:,}")


        st.markdown(f"**Spendable XP:** {spendable:,}")
        if spendable >= CHEQUE_COST and user.get("total_xp", 0) >= NEXT_CHEQUE_THRESHOLD:
            if st.button("Buy 5% Discount Cheque"):
                buy_discount_cheque(st.session_state.user_id)

        streak = db.update_streak(st.session_state.user_id)
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
            # FIX 5.2: Use 'name' from profile, fallback to 'email' if name is empty
            display_name = e.get('name') if e.get('name') else e['email']
            st.markdown(f"**{i+1}.** {display_name} ({e['total_xp']:,} XP)")


# SETTINGS TAB
def settings_tab():
    st.session_state.current_tab = "Settings"
    st.markdown("### Appearance")
    col1, col2 = st.columns(2)
    with col1:
        st.selectbox("Theme", list(THEMES.keys()), key="theme")
        st.selectbox("Font", FONTS, key="font")
    with col2:
        st.selectbox("Font Size", FONT_SIZES, key="font_size")

    st.markdown("### 2FA")
    if not db.is_2fa_enabled(st.session_state.user_id):
        if st.button("Enable 2FA"):
            secret, qr = db.enable_2fa(st.session_state.user_id)
            # FIX 4: Added output_format="PNG" for reliable QR code rendering
            st.image(qr, caption="Scan with Authenticator", output_format="PNG") 
            st.code(secret)
            award_xp(st.session_state.user_id, XP_RULES["2fa_enabled"], "2FA Enabled")
    else:
        st.success("2FA Enabled ✅")
        if st.button("Disable 2FA"):
            db.disable_2fa(st.session_state.user_id)
            st.success("2FA Disabled")

    st.markdown("### Profile")
    name = st.text_input("Name", st.session_state.user.get("name", ""))
    if st.button("Save Profile"):
        db.update_profile(st.session_state.user_id, name)
        award_xp(st.session_state.user_id, XP_RULES["profile_complete"], "Profile completed")

# Dummy Tabs (Replaced pdf_tab with implementation)
def chat_tab(): st.info("Chat Tutor content goes here...")
def progress_tab(): st.info("Progress dashboard content goes here...")

# FIX 2: Full PDF Q&A Tab Implementation
def pdf_tab():
    st.session_state.current_tab = "PDF Q&A"
    
    # 1. Upload & Context Setup
    if "pdf_chat_history" not in st.session_state:
        st.session_state.pdf_chat_history = []
        
    if not st.session_state.get("pdf_text"):
        st.markdown("### Upload Document for Q&A")
        uploaded_file = st.file_uploader("Upload a PDF document (Max 5MB)", type="pdf")
        
        if uploaded_file:
            # Enforce access limit check (for basic tier)
            if get_user_tier() == "basic" and db.get_daily_pdf_count(st.session_state.user_id) >= 3:
                st.error("You've used your **3 PDF uploads** today. Upgrade to Premium!")
                return
            
            # Extract PDF text
            pdf_bytes = uploaded_file.read()
            # Note: The ai_engine.extract_text_from_pdf expects 'self' (the instance) as the first argument.
            text = ai_engine.extract_text_from_pdf(ai_engine, pdf_bytes) 
            
            if text.startswith("Error"):
                st.error(text)
                return

            st.session_state.pdf_text = text
            st.session_state.pdf_filename = uploaded_file.name
            
            # Award XP and log usage
            db.increment_daily_pdf(st.session_state.user_id)
            award_xp(st.session_state.user_id, XP_RULES["pdf_upload"], "PDF Uploaded")
            st.toast("PDF processed! Ask your questions below.")
            st.rerun() # Rerun to show the Q&A interface
        return # Stop if context isn't set yet

    # 2. Q&A Interface
    st.success(f"Context from: **{st.session_state.pdf_filename}**")
    
    # Display chat history
    for entry in st.session_state.pdf_chat_history:
        with st.chat_message(entry["role"]):
            st.markdown(entry["content"])

    prompt = st.chat_input("Ask a question about the PDF content...")
    
    if prompt:
        st.session_state.pdf_chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Build system prompt with PDF context
        # Truncate text to 100,000 characters (approx 25,000 tokens) for token safety
        pdf_context_prompt = f"You are a helpful Kenyan tutor. Answer the user's question ONLY based on the following PDF content. If the answer is not in the text, state so.\n\n--- PDF Content ---\n{st.session_state.pdf_text[:100000]}\n-------------------" 
        
        # Generate streaming response
        with st.chat_message("assistant"):
            full_response = ""
            response_area = st.empty()
            response_generator = ai_engine.stream_response(prompt, pdf_context_prompt)
            for chunk in response_generator:
                full_response += chunk
                response_area.markdown(full_response + "▌")
            response_area.markdown(full_response)
        
        # Log and award XP
        # The 'subject' is the PDF filename here for logging purposes
        db.add_chat_history(st.session_state.user_id, st.session_state.pdf_filename, prompt, full_response)
        award_xp(st.session_state.user_id, XP_RULES["pdf_question"], "Asked PDF Question")
        st.session_state.pdf_chat_history.append({"role": "assistant", "content": full_response})

    # 3. Clear/Reset Button
    if st.button("Clear PDF Context", help="Start a new PDF Q&A session"):
        st.session_state.pdf_text = ""
        st.session_state.pdf_filename = ""
        st.session_state.pdf_chat_history = []
        st.rerun()

def exam_tab(): st.info("Exam Prep content goes here...")
def essay_tab(): st.info("Essay Grader content goes here...")
def premium_tab(): st.info("Premium Upgrade content goes here...")
def admin_dashboard(): st.info("Admin Dashboard content goes here...")

# MAIN
def main():
    try:
        init_session()
        apply_theme()
        if st.session_state.show_welcome: welcome_screen(); return
        login_block()
        if not st.session_state.logged_in: st.info("Log in to start learning! 📖"); return
        sidebar()
        enforce_access()

        tabs = ["Chat Tutor", "Progress", "Settings"]
        if get_user_tier() in ["premium", "admin"]:
            tabs += ["PDF Q&A", "Exam Prep", "Essay Grader"]
        if get_user_tier() == "basic":
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
                # Use st.session_state to track the current tab for access enforcement
                st.session_state.current_tab = name
                tab_map[name]()
    except Exception as e:
        st.error(f"CRASH: {e}")

if __name__ == "__main__":
    main()
