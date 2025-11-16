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

# ==============================================================================
# ANIMATION & STYLING (NON-STATIC LOGIN PAGE)
# ==============================================================================

# Simple CSS-based animation for a non-static login page banner
ANIMATION_CSS = """
<style>
@keyframes pulse {
    0% { transform: scale(1); opacity: 0.8; }
    50% { transform: scale(1.02); opacity: 1; }
    100% { transform: scale(1); opacity: 0.8; }
}
.animated-banner {
    text-align: center;
    padding: 15px;
    background: linear-gradient(45deg, #1C3144, #4CAF50); /* Gradient background */
    border-radius: 12px;
    margin-bottom: 25px;
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2);
    animation: pulse 3s infinite; /* Non-static animation */
    color: white;
    font-size: 1.3em;
    font-weight: 600;
}
</style>
"""

# ==============================================================================
# GAMIFICATION: LEVELS + XP SYSTEM
# ==============================================================================
LEVELS = {
    1: 0, 2: 100, 3: 250, 4: 500, 5: 1000,
    6: 2000, 7: 3500, 8: 6000, 9: 10000, 10: 15000,
    11: 25000, 12: 40000, 13: 60000, 14: 90000, 15: 130000
}

BASIC_MAX_LEVEL = 5 

XP_RULES = {
    "question_asked": 10,
    "pdf_upload": 30,
    "pdf_question": 15,
    "exam_10_percent": 1,
    "essay_5_percent": 1,
    "perfect_score": 100,
}

# ==============================================================================
# SESSION STATE AND UTILS
# ==============================================================================

def init_session():
    """Initializes necessary session state variables."""
    if 'db' not in st.session_state:
        st.session_state.db = Database()
    if 'ai_engine' not in st.session_state:
        # Assuming GEMINI_API_KEY is available in st.secrets
        st.session_state.ai_engine = AIEngine(gemini_key=st.secrets.get("GEMINI_API_KEY", "")) 
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'user_id' not in st.session_state:
        st.session_state.user_id = None
    if 'user_data' not in st.session_state:
        st.session_state.user_data = None
    if 'show_welcome' not in st.session_state:
        st.session_state.show_welcome = True
    if 'is_admin' not in st.session_state:
        st.session_state.is_admin = False
    if 'current_tab' not in st.session_state:
        st.session_state.current_tab = "Chat Tutor"
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    if 'pdf_text' not in st.session_state:
        st.session_state.pdf_text = ""
    if 'pdf_name' not in st.session_state:
        st.session_state.pdf_name = ""
    if 'show_forgot_password' not in st.session_state:
        st.session_state.show_forgot_password = False
    if 'reset_user_id' not in st.session_state:
        st.session_state.reset_user_id = None


def get_user_tier() -> str:
    """Returns user tier safely."""
    user_data = st.session_state.get('user_data')
    if not st.session_state.get('logged_in', False) or user_data is None:
        return "guest"
    
    if user_data.get("role") == "admin":
        st.session_state.is_admin = True
        return "admin"
    
    is_premium = user_data.get("is_premium", 0) == 1
    
    if is_premium:
        return "premium"
    
    return "basic"

# ==============================================================================
# PASSWORD RESET FUNCTIONS
# ==============================================================================

def update_password(user_id: int, new_password: str):
    """Updates the user's password hash in the database."""
    db = st.session_state.db
    hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
    
    db.conn.execute(
        "UPDATE users SET password_hash = ? WHERE user_id = ?",
        (hashed, user_id)
    )
    db.conn.commit()

def forgot_password_block():
    """
    Handles the 2FA-based password reset process.
    """
    db = st.session_state.db
    st.title("🔐 Password Reset (2FA Verification)")
    
    st.info("To reset your password, you must verify your identity using the 6-digit code from your Authenticator App.")

    # Step 1: Get Email/Identify User
    if st.session_state.reset_user_id is None:
        reset_email = st.text_input("Enter your registered Email Address")
        if st.button("Check Account"):
            user = db.get_user_by_email(reset_email)
            if user:
                # Check if 2FA is enabled for the user
                secret = db.get_2fa_secret(user['user_id'])
                if secret:
                    st.session_state.reset_user_id = user['user_id']
                    st.success("Account found! Proceed to 2FA verification below.")
                    st.rerun() # Rerun to move to the next step
                else:
                    st.error("2FA is not enabled for this account. Please contact support.")
            else:
                st.error("Email not found.")
        
        if st.button("← Back to Login", key="reset_back_login"):
            st.session_state.show_forgot_password = False
            st.rerun()
        return

    # Step 2: 2FA Verification and New Password Input
    user_id = st.session_state.reset_user_id
    secret = db.get_2fa_secret(user_id) # Retrieve the secret again

    st.subheader("2. Verify and Set New Password")
    
    with st.form("password_reset_form"):
        otp_code = st.text_input("6-Digit Authenticator Code", max_chars=6)
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        
        submitted = st.form_submit_button("Reset Password")
        
        if submitted:
            if new_password != confirm_password:
                st.error("New passwords do not match.")
            elif len(new_password) < 8:
                st.error("Password must be at least 8 characters long.")
            elif not secret:
                st.error("Error retrieving 2FA secret. Please restart the process.")
            else:
                try:
                    totp = pyotp.TOTP(secret)
                    if totp.verify(otp_code):
                        update_password(user_id, new_password)
                        st.success("✅ Password successfully reset! You can now log in.")
                        
                        # Cleanup session state and redirect to login
                        st.session_state.show_forgot_password = False
                        st.session_state.reset_user_id = None
                        st.session_state.logged_in = False
                        st.rerun()
                    else:
                        st.error("Invalid 2FA code. Please check your Authenticator App.")
                except Exception as e:
                    st.error(f"An error occurred during 2FA verification: {e}")

    if st.button("Cancel & Back to Login", key="reset_cancel_login"):
        st.session_state.show_forgot_password = False
        st.session_state.reset_user_id = None
        st.rerun()


# ==============================================================================
# LOGIN/AUTH FUNCTIONS
# ==============================================================================

def login_block():
    """
    Handles the login/registration forms.
    Shows the Forgot Password link ONLY on failed login.
    """
    db = st.session_state.db
    
    # Non-Static Animation Log-in Page
    st.markdown(ANIMATION_CSS, unsafe_allow_html=True)
    st.markdown('<div class="animated-banner">⚡ PrepKe AI: Accelerate Your Learning! 🎓</div>', unsafe_allow_html=True)
    
    st.title("PrepKe AI Tutor")
    
    login_tab, register_tab = st.tabs(["Login", "Register"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log In")

            if submitted:
                st.session_state.show_forgot_password = False # Reset flag on new attempt
                if not email or not password:
                    st.error("Please enter both email and password.")
                else:
                    with st.spinner("Authenticating..."):
                        user = db.get_user_by_email(email) 
                        
                        is_authenticated = False
                        
                        if user:
                            password_hash_bytes = user['password_hash']
                            
                            # CRASH FIX: Ensure hash is in bytes format for bcrypt
                            if isinstance(password_hash_bytes, str):
                                password_hash_bytes = password_hash_bytes.encode('utf-8')
                            
                            try:
                                if bcrypt.checkpw(password.encode('utf-8'), password_hash_bytes):
                                    is_authenticated = True
                            except Exception:
                                # Catch potential error if hash is corrupt or malformed
                                pass
                        
                        if is_authenticated:
                            st.session_state.logged_in = True
                            st.session_state.user_id = user['user_id']
                            st.session_state.email = user['email']
                            st.session_state.user_data = user
                            st.session_state.show_welcome = False
                            db.update_last_active(user['user_id'])
                            st.success("Login successful!")
                            st.rerun()
                        else:
                            st.error("Invalid email or password.")
                            st.session_state.logged_in = False
                            st.session_state.user_data = None
                            # Show forgot password link ONLY on failed login
                            st.session_state.show_forgot_password = True

        # Forgotten Password Link (Visible only after a failed login attempt)
        if st.session_state.show_forgot_password:
            if st.button("Forgot Password? Use 2FA Reset", key="forgot_pw_link"):
                st.session_state.show_forgot_password = True
                st.session_state.reset_user_id = None
                st.rerun()


    with register_tab:
        with st.form("register_form"):
            new_name = st.text_input("Name (Optional)", key="reg_name")
            new_email = st.text_input("Email", key="reg_email")
            new_password = st.text_input("Password", type="password", key="reg_password")
            confirm_password = st.text_input("Confirm Password", type="password", key="reg_confirm")
            reg_submitted = st.form_submit_button("Register")
            
            if reg_submitted:
                if not new_email or not new_password or not confirm_password:
                    st.error("Please fill in all required fields.")
                elif new_password != confirm_password:
                    st.error("Passwords do not match.")
                elif db.get_user_by_email(new_email):
                    st.error("An account with this email already exists.")
                else:
                    try:
                        db.add_user(new_email, new_password, new_name)
                        st.success("Registration successful! Please log in.")
                    except Exception as e:
                        st.error(f"Registration failed. Try a different email. Error: {e}")


def logout():
    """Logs out the user and clears essential session state."""
    st.session_state.logged_in = False
    st.session_state.user_id = None
    st.session_state.user_data = None
    st.session_state.is_admin = False
    st.session_state.pdf_text = ""
    st.session_state.pdf_name = ""
    st.session_state.chat_history = []
    st.session_state.show_welcome = True
    st.session_state.show_forgot_password = False
    st.session_state.reset_user_id = None
    st.rerun()

# ==============================================================================
# UI COMPONENTS (FIXES: apply_theme is now defined)
# ==============================================================================

def apply_theme():
    """FIXED: Sets the Streamlit page configuration."""
    st.set_page_config(
        page_title="PrepKe AI Tutor",
        layout="wide",
        initial_sidebar_state="expanded"
    )

def welcome_screen():
    st.title("PrepKe AI: Your Kenyan Curriculum Expert")
    st.info("Welcome! Log in or register to get started with your AI tutor.")
    if st.button("Proceed to Login"):
        st.session_state.show_welcome = False
        st.rerun()
        
def sidebar():
    """Generates the sidebar with user info and logout."""
    user_data = st.session_state.user_data 
    user_tier = get_user_tier()
    st.sidebar.header(f"Welcome, {user_data.get('name', user_data.get('email', 'User'))}!")
    st.sidebar.markdown(f"**Tier:** **`{user_tier.upper()}`**")
    st.sidebar.markdown(f"**XP:** {user_data.get('total_xp', 0)}")
    st.sidebar.markdown("---")
    if st.sidebar.button("Logout"):
        logout()

def enforce_access():
    """Placeholder for access control logic based on user tier."""
    pass

# ... rest of the tab functions stubs
def chat_tab(): st.info("Chat Tutor content goes here...")
def progress_tab(): st.info("Progress Tracking content goes here...")
def settings_tab(): st.info("Settings content goes here...")
def pdf_tab(): st.info("PDF Q&A content goes here...")
def exam_tab(): st.info("Exam Prep content goes here...")
def essay_tab(): st.info("Essay Grader content goes here...")
def premium_tab(): st.info("Premium Upgrade content goes here...")
def admin_dashboard(): st.info("Admin Dashboard content goes here...")


# ==============================================================================
# MAIN APPLICATION LOGIC
# ==============================================================================

def main():
    try:
        init_session()
        apply_theme() # This call is now correctly defined

        if st.session_state.show_welcome: 
            welcome_screen()
            return
        
        # Priority 1: Handle password reset flow
        if st.session_state.show_forgot_password:
            forgot_password_block()
            return

        # Priority 2: Handle login/register flow
        if not st.session_state.logged_in: 
            login_block()
            st.info("Log in to start learning! 📖") 
            return
        
        # Priority 3: Main App Content
        sidebar()
        enforce_access()
        
        user_tier = get_user_tier()

        tabs = ["Chat Tutor", "Progress", "Settings"]
        if user_tier in ["premium", "admin"]:
            tabs += ["PDF Q&A", "Exam Prep", "Essay Grader"]
        if user_tier == "basic":
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
        st.error(f"An unexpected error occurred: {e}")
        print(f"CRITICAL ERROR IN MAIN: {e}")

if __name__ == "__main__":
    main()
