# app.py - FIXED
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

# INIT - Use global variables for DB and AI Engine
try:
    db = Database()
    ai_engine = AIEngine(st.secrets.get("GEMINI_API_KEY", ""))
except Exception as e:
    pass

# SESSION STATE
def init_session():
    defaults = {
        "logged_in": False, "user_id": None, "is_admin": False, "user": None,
        "show_welcome": True, "chat_history": [], "current_subject": "Mathematics",
        "pdf_text": "", "current_tab": "Chat Tutor", "theme": "Kenya", "font": "Inter", "font_size": "Medium",
        "exam_questions": None, "user_answers": {}, "exam_submitted": False,
        "reset_user_id": None, "reset_step": 0
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# USER TIER
def get_user_tier():
    if st.session_state.is_admin: return "admin"
    user = db.get_user(st.session_state.user_id)
    if not user: return "basic"
    # Re-check admin status based on database for robustness
    if user.get("role") == "admin":
        st.session_state.is_admin = True
        return "admin"
        
    if user.get("is_premium") and db.check_premium_validity(st.session_state.user_id):
        return "premium"
    return "basic"

def enforce_access():
    tier = get_user_tier()
    tab = st.session_state.current_tab
    if tier == "admin": return
    
    premium_tabs = ["PDF Q&A", "Exam Prep", "Essay Grader"]
    if tier == "basic" and tab in premium_tabs:
        st.warning("Upgrade to **Premium** to access this feature.")
        st.stop()
        
    if tier == "basic":
        if tab == "Chat Tutor":
            if hasattr(db, 'get_daily_question_count') and db.get_daily_question_count(st.session_state.user_id) >= 10:
                st.error("You've used your **10 questions** today. Upgrade to Premium!")
                st.stop()
        if tab == "PDF Q&A":
            if hasattr(db, 'get_daily_pdf_count') and db.get_daily_pdf_count(st.session_state.user_id) >= 3:
                st.error("You've used your **3 PDF uploads** today. Upgrade to Premium!")
                st.stop()

# GAMIFICATION
@st.cache_data(ttl=600) # Cache level calculation for 10 minutes
def get_user_level(user_data):
    total_xp = user_data.get("total_xp", 0)
    spendable_xp = user_data.get("spendable_xp", total_xp)
    tier = get_user_tier()
    max_level = float('inf') if tier != "basic" else BASIC_MAX_LEVEL

    level = 1
    for lvl, req in LEVELS.items():
        if total_xp >= req and lvl <= max_level:
            level = lvl
            
    level_list = sorted(LEVELS.keys())
    current_level_xp = LEVELS.get(level, 0)
    
    next_lvl = level + 1
    
    if next_lvl > level_list[-1] or level >= max_level:
        current = total_xp - current_level_xp
        next_xp = float('inf')
        progress_percent = 100.0
    else:
        xp_for_next = LEVELS.get(next_lvl, float('inf'))
        xp_to_next = xp_for_next - current_level_xp
        xp_earned_in_level = total_xp - current_level_xp
        
        current = xp_earned_in_level
        next_xp = xp_to_next
        progress_percent = (current / next_xp) * 100

    return level, current, next_xp, spendable_xp, progress_percent

def award_xp(user_id, points, reason):
    if hasattr(db, 'add_xp'):
        db.add_xp(user_id, points)
        st.toast(f"**+{points} XP** – {reason} 🎉")

def buy_discount_cheque(user_id):
    user = db.get_user(user_id)
    spendable = user.get("spendable_xp", 0)
    
    if spendable < CHEQUE_COST:
        st.error("Not enough spendable XP!")
        return
        
    if not hasattr(db, 'deduct_spendable_xp') or not hasattr(db, 'add_discount'):
        st.error("Database functions missing for this feature.")
        return
    
    if db.deduct_spendable_xp(user_id, CHEQUE_COST):
        db.add_discount(user_id, 5)
        st.success("**5% Discount Cheque Bought!** Premium now 5% off! 💰")
        st.rerun()

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
            if user and hasattr(db, 'is_2fa_enabled') and db.is_2fa_enabled(user["user_id"]):
                st.success("2FA code sent to your authenticator! (Placeholder)")
                st.session_state.reset_user_id = user["user_id"]
                st.session_state.reset_step = 1
            else:
                st.error("No 2FA-enabled account found for this email.")
        if st.session_state.get("reset_step") == 1:
            code = st.text_input("2FA Code")
            if st.button("Verify"):
                if hasattr(db, 'verify_2fa_code') and db.verify_2fa_code(st.session_state.reset_user_id, code):
                    st.session_state.reset_step = 2
                else:
                    st.error("Invalid code.")
        if st.session_state.get("reset_step") == 2:
            new_pwd = st.text_input("New Password", type="password")
            confirm = st.text_input("Confirm", type="password")
            if st.button("Reset"):
                if new_pwd == confirm and len(new_pwd) >= 6:
                    if hasattr(db, 'update_password'):
                        db.update_password(st.session_state.reset_user_id, new_pwd)
                        st.success("Password reset! Log in.")
                        st.session_state.reset_step = 0
                        st.session_state.show_welcome = False
                        st.rerun()
                    else:
                        st.error("Database update function missing.")
                else:
                    st.error("Passwords must match and be ≥6 chars.")
        return

    email = st.text_input("Email", key=f"{choice.lower()}_email")
    pwd = st.text_input("Password", type="password", key=f"{choice.lower()}_pwd")
    totp = st.text_input("2FA Code", key="totp") if choice == "Login" else ""

    if st.button(choice, type="primary"):
        if choice == "Sign Up":
            if len(pwd) < 6: st.error("Password ≥6 chars."); return
            uid = db.add_user(email, pwd) if hasattr(db, 'add_user') else None
            if uid:
                award_xp(uid, 50, "First Login")
                st.success("Account created! +50 XP 🥳")
            else:
                st.error("Email exists or database error.")
            return

        user = db.get_user_by_email(email)
        if not user: st.error("Invalid email/password."); return

        stored_hash = user["password_hash"]
        if isinstance(stored_hash, str): stored_hash = stored_hash.encode()
        
        if not bcrypt.checkpw(pwd.encode('utf-8'), stored_hash): st.error("Invalid email/password."); return

        if hasattr(db, 'is_2fa_enabled') and db.is_2fa_enabled(user["user_id"]) and (not hasattr(db, 'verify_2fa_code') or not db.verify_2fa_code(user["user_id"], totp)):
            st.error("Invalid 2FA code.")
            return

        if hasattr(db, 'update_user_activity'):
            db.update_user_activity(user["user_id"])
        
        is_admin = user.get("role") == "admin"
        
        st.session_state.update({
            "logged_in": True, "user_id": user["user_id"], "is_admin": is_admin, "user": user
        })
        award_xp(user["user_id"], 20, "Daily login")
        st.rerun()

def sidebar():
    with st.sidebar:
        apply_theme()
        st.markdown("## PrepKe AI 🇰🇪")
        tier = get_user_tier()
        st.markdown(f"**Tier:** `{tier.upper()}`")

        user = db.get_user(st.session_state.user_id)
        st.session_state.user = user
        level, current, next_xp, spendable, progress_percent = get_user_level(user)
        st.markdown(f"### Level {level} {'(Max)' if tier == 'basic' and level == BASIC_MAX_LEVEL else ''}")
        
        if next_xp != float('inf'):
            st.progress(progress_percent / 100.0)
            st.caption(f"**{current:,}/{next_xp:,} XP** to next level")
        else:
            st.progress(1.0)
            st.success(f"Max Level Reached! XP: {current:,}")


        st.markdown(f"**Spendable XP:** {spendable:,}")
        if spendable >= CHEQUE_COST:
            if st.button("Buy 5% Discount Cheque"):
                buy_discount_cheque(st.session_state.user_id)

        streak = db.update_streak(st.session_state.user_id) if hasattr(db, 'update_streak') else 0
        st.markdown(f"**Streak:** {streak} days 🔥")

        st.session_state.current_subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))

        badges = json.loads(user.get("badges", "[]"))
        if badges:
            st.markdown("### Badges 🥇")
            for b in badges[:6]:
                st.markdown(f"<span class='badge'>{BADGES.get(b, b)}</span>", unsafe_allow_html=True)

        st.markdown("### National Leaderboard 🌍")
        lb = db.get_xp_leaderboard()[:5] if hasattr(db, 'get_xp_leaderboard') else []
        
        for i, e in enumerate(lb):
            st.markdown(f"**{i+1}.** {e.get('email', 'User')} ({e.get('total_xp', 0):,} XP)")
            
        if st.sidebar.button("Log Out 👋", type="secondary", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_id = None
            st.session_state.user = None
            st.session_state.is_admin = False
            st.rerun()

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
    if hasattr(db, 'is_2fa_enabled') and not db.is_2fa_enabled(st.session_state.user_id):
        if st.button("Enable 2FA"):
            if hasattr(db, 'enable_2fa'):
                secret, qr = db.enable_2fa(st.session_state.user_id)
                st.image(qr, caption="Scan with Authenticator")
                st.code(secret)
                award_xp(st.session_state.user_id, 20, "2FA Enabled")
    else:
        st.success("2FA Enabled ✅")
        if st.button("Disable 2FA"):
            if hasattr(db, 'disable_2fa'):
                db.disable_2fa(st.session_state.user_id)
                st.success("2FA Disabled")

    st.markdown("### Profile")
    name = st.text_input("Name", st.session_state.user.get("name", ""))
    if st.button("Save Profile"):
        if hasattr(db, 'update_profile'):
            db.update_profile(st.session_state.user_id, name)
            award_xp(st.session_state.user_id, 30, "Profile completed")

# Other Tabs (Dummy implementations)
def chat_tab(): st.session_state.current_tab = "Chat Tutor"; st.info("Chat Tutor content goes here...")
def progress_tab(): st.session_state.current_tab = "Progress"; st.info("Progress dashboard content goes here...")
def pdf_tab(): st.session_state.current_tab = "PDF Q&A"; st.info("PDF Q&A content goes here...")
def exam_tab(): st.session_state.current_tab = "Exam Prep"; st.info("Exam Prep content goes here...")
def essay_tab(): st.session_state.current_tab = "Essay Grader"; st.info("Essay Grader content goes here...")
def premium_tab(): st.session_state.current_tab = "Premium"; st.info("Premium Upgrade content goes here...")


# ADMIN DASHBOARD - ENFORCING SINGLE PERMANENT ADMIN
def admin_dashboard():
    st.session_state.current_tab = "Admin"
    st.title("👑 Admin Dashboard (Locked)")
    st.warning("This tab is strictly for the Administrator account only. **The Admin Role Management tool is disabled to enforce a single, permanent administrator.**")
    st.divider()
    
    # 1. Pending Payments
    st.header("1. Pending Premium Payments")
    
    pending_payments = db.get_pending_payments() if hasattr(db, 'get_pending_payments') else []
    
    if pending_payments:
        for payment in pending_payments:
            with st.expander(f"**{payment.get('email', f'User {payment.get('user_id', 'Unknown')}')}** - Code: {payment.get('mpesa_code', 'N/A')}"):
                st.markdown(f"**Phone:** {payment.get('phone', 'N/A')} - **Submitted:** {payment.get('timestamp', 'N/A')}")
                col_a, col_r, _ = st.columns([1, 1, 4])
                with col_a:
                    if st.button("✅ Approve", key=f"approve_{payment['id']}"):
                        if hasattr(db, 'approve_manual_payment'):
                            db.approve_manual_payment(payment['id']) 
                            st.success(f"Approved Premium for {payment.get('email', 'user')}.")
                            st.rerun()
                with col_r:
                    if st.button("❌ Reject", key=f"reject_{payment['id']}"):
                        if hasattr(db, 'reject_manual_payment'):
                            db.reject_manual_payment(payment['id']) 
                            st.error(f"Rejected payment for {payment.get('email', 'user')}.")
                            st.rerun()
        st.divider()
    else:
        st.info("No pending payments to review.")

    # 2. Leaderboard Winners
    st.header("2. Leaderboard Winners (Automatic 20% Discount)")
    flagged_users = db.get_flagged_for_discount() if hasattr(db, 'get_flagged_for_discount') else []
    
    if flagged_users:
        for user in flagged_users:
            discount_status = "Granted" if user.get('discount', 0) >= 20 else "Pending Approval"
            user_name = user.get("name") or user.get("email")
            
            with st.expander(f"**{user_name}** - Status: {discount_status}"):
                st.markdown(f"**Win Streak:** {user.get('leaderboard_win_streak', 0)} days - **Current Discount:** {user.get('discount', 0)}%")
                
                if user.get('discount', 0) < 20:
                    if st.button("Apply Automatic 20% Cheque", key=f"apply_auto_{user['user_id']}"):
                        if hasattr(db, 'add_discount'):
                            db.add_discount(user['user_id'], 20)
                            st.success(f"20% Cheque applied for {user_name}.")
                            st.rerun()
            st.divider()
    else:
        st.info("No users currently qualify for the automatic 20% discount.")
    
    st.divider()
    st.markdown("### ⚠️ Security Notice")
    st.error("The administrative function to change user roles has been removed from the UI to ensure the admin account is held permanently and exclusively by the designated user.")

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
                st.session_state.current_tab = name
                tab_map[name]()
    except Exception as e:
        st.error(f"CRASH: {e}")
        import traceback
        st.code(traceback.format_exc())

if __name__ == "__main__":
    main()
