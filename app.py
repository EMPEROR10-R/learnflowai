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
# CONFIGURATION & SETUP
# ==============================================================================
# CSS to hide Streamlit UI elements
HIDE_STREAMLIT_UI = """
<style>
#MainMenu {visibility: hidden;} footer {visibility: hidden;} 
.st-emotion-cache-1jm6hrl, .st-emotion-cache-1h9z3y {visibility: hidden;} 
.animated-banner {text-align: center; padding: 15px; background: linear-gradient(45deg, #1C3144, #4CAF50); border-radius: 12px; margin-bottom: 25px; box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2); animation: pulse 3s infinite; color: white; font-size: 1.3em; font-weight: 600;}
@keyframes pulse {0% { transform: scale(1); opacity: 0.8; } 50% { transform: scale(1.02); opacity: 1; } 100% { transform: scale(1); opacity: 0.8; }}
.stProgress > div > div > div > div {background-color: #4CAF50;}
</style>
"""

LEVELS = {
    1: 0, 2: 100, 3: 250, 4: 500, 5: 1000,
    6: 2000, 7: 3500, 8: 6000, 9: 10000, 10: 15000,
    11: 25000, 12: 40000, 13: 60000, 14: 90000, 15: 130000
}
BASIC_MAX_LEVEL = 5  
XP_RULES = {"question_asked": 10, "pdf_upload": 30, "pdf_question": 15, "exam_10_percent": 1, "essay_5_percent": 1, "perfect_score": 100}
CHEQUE_5_PERCENT_COST = 1_000_000
CHEQUE_20_PERCENT_COST = 50_000_000
MAX_DISCOUNT_PERCENT = 50

# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def apply_theme():
    st.set_page_config(page_title="PrepKe AI Tutor", layout="wide", initial_sidebar_state="expanded")
    st.markdown(HIDE_STREAMLIT_UI, unsafe_allow_html=True)
    st.markdown('<div class="animated-banner">⚡ PrepKe AI: Accelerate Your Learning! 🎓</div>', unsafe_allow_html=True)


def init_session():
    """Initializes necessary session state variables."""
    if 'db' not in st.session_state: st.session_state.db = Database()
    if 'ai_engine' not in st.session_state: 
        key = st.secrets.get("GEMINI_API_KEY", "DUMMY_KEY_FOR_STUBS") 
        st.session_state.ai_engine = AIEngine(gemini_key=key) 
    if 'logged_in' not in st.session_state: st.session_state.logged_in = False
    if 'user_id' not in st.session_state: st.session_state.user_id = None
    if 'user_data' not in st.session_state: st.session_state.user_data = None
    if 'show_welcome' not in st.session_state: st.session_state.show_welcome = False # Start directly at login
    if 'is_admin' not in st.session_state: st.session_state.is_admin = False
    if 'current_tab' not in st.session_state: st.session_state.current_tab = "Chat Tutor"
    if 'chat_history' not in st.session_state: st.session_state.chat_history = []
    if 'pdf_text' not in st.session_state: st.session_state.pdf_text = ""
    if 'pdf_name' not in st.session_state: st.session_state.pdf_name = ""
    if 'show_forgot_password' not in st.session_state: st.session_state.show_forgot_password = False
    if 'reset_user_id' not in st.session_state: st.session_state.reset_user_id = None
    if 'exam_questions' not in st.session_state: st.session_state.exam_questions = None
    if 'essay_in_progress' not in st.session_state: st.session_state.essay_in_progress = None
    if 'user_tier' not in st.session_state: st.session_state.user_tier = "guest"


def get_user_tier(db: Database, user_id: int) -> str:
    """Determines the user's current access tier."""
    user = db.get_user(user_id) 
    if not st.session_state.get('logged_in', False) or user is None:
        st.session_state.user_tier = "guest"
        return "guest"
    
    st.session_state.is_admin = (user.get("role") == "admin")
    if st.session_state.is_admin: 
        st.session_state.user_tier = "admin"
        return "admin"
    
    if user.get("is_premium") and db.check_premium_validity(user_id):
        st.session_state.user_tier = "premium"
        return "premium"
    
    st.session_state.user_tier = "basic"
    return "basic"

@st.cache_data(ttl=600)
def get_user_level(user_data):
    """Calculates the current level, XP required for the next level, and progress percentage."""
    total_xp = user_data.get("total_xp", 0)
    level = 1
    current_level_xp = 0
    level_list = sorted(LEVELS.keys())
    tier = st.session_state.get('user_tier', 'basic')
    max_level = float('inf') if tier != "basic" else BASIC_MAX_LEVEL
    
    for lvl in level_list:
        if total_xp >= LEVELS[lvl] and lvl <= max_level:
            level = lvl
            current_level_xp = LEVELS[lvl]
        elif lvl > max_level:
            break

    next_lvl = level + 1
    if next_lvl > level_list[-1] or level >= max_level:
        progress = 1.0
        xp_required = 0
        xp_to_next = 0
        level_cap_msg = "Level Cap Reached!" if level >= max_level else "Max Level Reached!"
    else:
        xp_for_next = LEVELS.get(next_lvl, float('inf'))
        xp_to_next = xp_for_next - current_level_xp
        xp_earned_in_level = total_xp - current_level_xp
        progress = xp_earned_in_level / xp_to_next
        xp_required = xp_to_next - xp_earned_in_level
        level_cap_msg = f"{xp_required:,} XP to Level {next_lvl}"

    return level, progress, level_cap_msg, user_data.get("spendable_xp", 0)


def enforce_access(db: Database):
    """Enforces tier limits and access restrictions."""
    tier = get_user_tier(db, st.session_state.user_id)
    tab = st.session_state.current_tab
    
    if tier == "admin": return
    
    premium_tabs = ["PDF Q&A", "Exam Prep", "Essay Grader"]
    if tier == "basic" and tab in premium_tabs:
        st.warning("Upgrade to **Premium** to access this feature.")
        st.stop()
        
    if tier == "basic":
        if tab == "Chat Tutor":
            if db.get_daily_question_count(st.session_state.user_id) >= 10:
                st.error("You've used your **10 free questions** today. Upgrade to Premium for unlimited chat.")
                st.stop()
        if tab == "PDF Q&A":
            if db.get_daily_pdf_count(st.session_state.user_id) >= 3:
                st.error("You've used your **3 free PDF uploads** today. Upgrade to Premium for unlimited access.")
                st.stop()
    
    user = db.get_user(st.session_state.user_id)
    level, _, _, _ = get_user_level(user)
    if tier == "basic" and level >= BASIC_MAX_LEVEL and user.get("total_xp", 0) >= LEVELS.get(BASIC_MAX_LEVEL + 1, float('inf')):
        st.warning(f"You have reached the **Level {BASIC_MAX_LEVEL} Cap** for Basic users! Upgrade to Premium to continue leveling up and unlock more features.")
        st.stop()

# ==============================================================================
# SIDEBAR AND AUTH PLACEHOLDERS (To make main() runnable)
# ==============================================================================

def sidebar(db: Database):
    """Generates the main sidebar with the full XP bar and user details."""
    user_data = db.get_user(st.session_state.user_id)
    tier = get_user_tier(db, st.session_state.user_id)
    name = user_data.get("name") or user_data.get("email").split('@')[0]
    
    st.sidebar.markdown(f"### Welcome, **{name}**!")
    st.sidebar.markdown(f"**Tier:** <span style='color:#FFD700; font-weight:bold;'>{tier.upper()}</span>", unsafe_allow_html=True)
    
    level, progress, level_cap_msg, xp_coins = get_user_level(user_data)
    
    st.sidebar.markdown(f"**Level {level}** (Total XP: {user_data['total_xp']:,})")
    st.sidebar.progress(progress)
    st.sidebar.caption(level_cap_msg)
    st.sidebar.markdown(f"#### 💰 XP Coins: **{xp_coins:,}**", unsafe_allow_html=True)
    
    if tier == 'basic':
        q_count = db.get_daily_question_count(st.session_state.user_id)
        pdf_count = db.get_daily_pdf_count(st.session_state.user_id)
        
        st.sidebar.info(
            f"**Daily Limits:**\n"
            f"- Chat Questions: {q_count}/10\n"
            f"- PDF Uploads: {pdf_count}/3\n"
            f"Upgrade to Premium for unlimited access!"
        )

    if st.sidebar.button("Log Out 👋", type="secondary"):
        st.session_state.logged_in = False
        st.session_state.user_id = None
        st.session_state.user_data = None
        st.rerun()

def update_password(user_id: int, new_password: str):
    db = st.session_state.db
    hashed = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
    db.conn.execute("UPDATE users SET password_hash = ? WHERE user_id = ?", (hashed, user_id))
    db.conn.commit()

def forgot_password_block():
    db = st.session_state.db
    st.title("🔐 Password Reset (2FA Verification)")
    st.info("Authenticator App verification is required to reset your password.")
    # Simplified placeholder logic
    if st.button("Cancel & Back to Login"):
        st.session_state.show_forgot_password = False
        st.session_state.reset_user_id = None
        st.rerun()

def login_block():
    db = st.session_state.db
    st.title("PrepKe AI Tutor")
    login_tab, register_tab = st.tabs(["Login", "Register"])

    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log In")

            if submitted:
                user = db.get_user_by_email(email) 
                is_authenticated = False
                if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash']):
                    is_authenticated = True
                
                if is_authenticated:
                    st.session_state.logged_in = True
                    st.session_state.user_id = user['user_id']
                    st.session_state.user_data = user
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Invalid email or password.")
                    if st.button("Forgot Password? Use 2FA Reset"):
                        st.session_state.show_forgot_password = True
                        st.rerun()

    with register_tab:
        with st.form("register_form"):
            new_email = st.text_input("Email", key="reg_email")
            new_password = st.text_input("Password", type="password", key="reg_password")
            reg_submitted = st.form_submit_button("Register")
            if reg_submitted:
                if not db.get_user_by_email(new_email):
                    db.add_user(new_email, new_password)
                    st.success("Registration successful! Please log in.")
                else:
                    st.error("An account with this email already exists.")

def welcome_screen():
    st.title("Welcome to PrepKe AI!")
    if st.button("Start Learning"):
        st.session_state.show_welcome = False
        st.rerun()

# ==============================================================================
# TAB IMPLEMENTATIONS (Crucial Fixes in Chat/PDF Tabs)
# ==============================================================================

def chat_tab(db: Database):
    st.title("🗣️ Chat Tutor")
    col1, col2 = st.columns([1, 2])
    with col1:
        subject = st.selectbox("Select Subject", list(SUBJECT_PROMPTS.keys()), key="chat_subject")
        if st.button("Clear Chat", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()

    with col2:
        for message in st.session_state.chat_history:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        prompt = st.chat_input(f"Ask your question about {subject}...")
        
        if prompt:
            # FIX 1: Correctly call the new database increment function
            db.increment_daily_question(st.session_state.user_id) 
            
            with st.spinner(f"AI Tutor is thinking..."):
                time.sleep(1)
                ai_response = f"Placeholder response for your question about **{subject}**: '{prompt}'. The Chat Tutor feature is now fully structured and working. You earned **+10 XP** for asking a question!"
                
                xp_gain = XP_RULES["question_asked"]
                db.add_xp(st.session_state.user_id, xp_gain, xp_gain)
                st.session_state.chat_history.append({"role": "user", "content": prompt})
                st.session_state.chat_history.append({"role": "assistant", "content": ai_response})
                st.toast(f"**+{xp_gain} XP** – Question Asked 🎉")
                st.rerun()


def progress_tab(db: Database):
    """Displays the user's personal progress and the National Leaderboards."""
    st.title("📈 Progress & National Ranking")
    user_data = db.get_user(st.session_state.user_id)
    
    st.header("My Performance Summary")
    st.metric(label="Current Discount Cheque Value", value=f"{user_data.get('discount', 0)}%", delta="Can be used on your next Premium payment.")
    st.metric(label="Leaderboard Win Streak (2-week check)", value=f"{user_data.get('leaderboard_win_streak', 0)} days", delta="Top 2+ boards for 14 days to win 20% discount!")
    st.divider()

    st.header("🏆 National Ranking")
    
    col_xp, col_exam, col_essay = st.columns(3)

    # 1. Level Leaderboard (Highest Level/XP)
    with col_xp:
        st.subheader("1. Level Ranking (Total XP)")
        lb_xp = db.get_xp_leaderboard(limit=10)
        
        if lb_xp:
            data = [{"Rank": i+1, "Name": e['name'] or e['email'].split('@')[0], "Total XP": f"{e['total_xp']:,}"} for i, e in enumerate(lb_xp)]
            df = pd.DataFrame(data).set_index("Rank")
            st.dataframe(df, use_container_width=True, hide_index=False)
        else:
            st.info("No XP data available yet.")

    # 2. Top Exam Scores
    with col_exam:
        st.subheader("2. Top Exam Scores")
        lb_exam = db.get_exam_leaderboard(limit=10)
        if lb_exam:
            data = [{"Rank": i+1, "Name": e['name'] or e['email'].split('@')[0], "Score": f"{e['max_score']}%", "Subject": e['subject']} for i, e in enumerate(lb_exam)]
            df = pd.DataFrame(data).set_index("Rank")
            st.dataframe(df, use_container_width=True, hide_index=False)
        else:
            st.info("No Exam scores recorded yet.")

    # 3. Top Essay Scores
    with col_essay:
        st.subheader("3. Top Essay Scores")
        lb_essay = db.get_essay_leaderboard(limit=10)
        if lb_essay:
            data = [{"Rank": i+1, "Name": e['name'] or e['email'].split('@')[0], "Score": f"{e['max_score']}%", "Topic": e['topic']} for i, e in enumerate(lb_essay)]
            df = pd.DataFrame(data).set_index("Rank")
            st.dataframe(df, use_container_width=True, hide_index=False)
        else:
            st.info("No Essay scores recorded yet.")
    
    st.button("Simulate Daily Leaderboard Check (Admin function)", key="sim_lb_check", disabled=True)


def pdf_tab(db: Database):
    st.title("📚 PDF Q&A")
    st.info("Upload your notes/texts (e.g., scheme of work, past paper) and ask the AI about them.")
    
    uploaded_file = st.file_uploader("Upload a PDF file", type=["pdf"], key="pdf_uploader")
    
    if uploaded_file and st.session_state.get('pdf_name') != uploaded_file.name:
        # FIX 2: Correctly call the new database increment function
        db.increment_daily_pdf(st.session_state.user_id)
        
        with st.spinner("Extracting text from PDF..."):
            time.sleep(2)
            st.session_state.pdf_text = f"Simulated text from '{uploaded_file.name}'."
            st.session_state.pdf_name = uploaded_file.name
            xp_gain = XP_RULES["pdf_upload"]
            db.add_xp(st.session_state.user_id, xp_gain, xp_gain)
            st.toast(f"**+{xp_gain} XP** – PDF Uploaded 🎉")
            st.rerun()

    if st.session_state.pdf_text:
        st.subheader(f"Active Document: {st.session_state.pdf_name}")
        user_query = st.text_input("Ask a question about this document:")
        if user_query and st.button("Get Answer"):
            # Ensure question is also counted against daily limit
            db.increment_daily_question(st.session_state.user_id) 
            
            with st.spinner("Generating answer from PDF context..."):
                time.sleep(1)
                xp_gain = XP_RULES["pdf_question"]
                db.add_xp(st.session_state.user_id, xp_gain, xp_gain)
                st.success(f"Answer for '{user_query}' generated. (**+15 XP** earned!)")
                st.toast(f"**+{xp_gain} XP** – PDF Questioned 🎉")
                st.rerun()


def exam_tab(db: Database):
    st.title("📝 Exam Prep Generator")
    st.info("Generate custom practice exams for KCSE/KPSEA subjects.")
    
    st.selectbox("Exam Type", ["KCSE", "KPSEA"], key="exam_type")
    st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()), key="exam_subject")
    st.slider("Number of Questions", 5, 25, 10, key="exam_count")
    
    if st.button("Generate Exam", type="primary"):
        with st.spinner("Generating exam questions..."):
            time.sleep(2)
            st.session_state.exam_questions = [{"id": i, "question": f"Question {i+1}...", "options": ["A", "B", "C", "D"], "answer": "B"} for i in range(st.session_state.exam_count)]
            st.session_state.exam_submitted = False
            st.success("Exam generated! Start answering below.")
            st.rerun()

    if st.session_state.get('exam_questions') and not st.session_state.get('exam_submitted'):
        st.subheader("Your Practice Exam")
        user_answers = {}
        for q in st.session_state.exam_questions:
            user_answers[q['id']] = st.radio(q['question'], q['options'], key=f"q_{q['id']}")

        if st.button("Submit Exam & Get Score", type="primary"):
            score = 75 # Simulated score
            details = json.dumps({"score": score, "answers": user_answers})
            
            db.log_exam_score(st.session_state.user_id, st.session_state.exam_subject, score, details)
            st.session_state.exam_submitted = True
            
            xp_earned = score // 10
            st.toast(f"**+{xp_earned} XP** – Exam Submitted 🎉")
            st.rerun()

    if st.session_state.get('exam_submitted'):
        st.success(f"You scored 75% on the {st.session_state.exam_subject} exam! Check your Progress tab for ranking.")
        st.button("Start a New Exam")


def essay_tab(db: Database):
    st.title("✍️ Essay Grader")
    st.info("Write your essay and get a score, feedback, and tips based on the Kenyan curriculum.")
    
    topic = st.text_input("Essay Topic:", "Discuss the impact of devolution in Kenyan counties.")
    essay_text = st.text_area("Write your full essay here (Min 250 words)", height=300)
    
    if st.button("Grade Essay", type="primary") and len(essay_text.split()) >= 10:
        with st.spinner("Sending essay to AI Grader..."):
            time.sleep(3)
            score = 85 
            feedback = "Excellent structure and compelling arguments! Focus on citing more contemporary data."
            
            db.log_essay_score(st.session_state.user_id, topic, score, feedback, essay_text)
            
            xp_earned = score // 5 
            st.subheader(f"Grade: **{score}/100**")
            st.markdown(f"**Detailed Feedback:** {feedback}")
            st.toast(f"**+{xp_earned} XP** – Essay Graded 🎉")
    elif st.button("Grade Essay", type="primary"):
        st.error("Please write a longer essay (minimum 10 words for this demo).")


def premium_tab(db: Database):
    st.title("🌟 Premium & XP Coin Store")
    user = db.get_user(st.session_state.user_id)
    xp_coins = user.get("spendable_xp", 0)
    current_discount = user.get("discount", 0)
    
    st.header("Upgrade to Premium")
    st.info(f"The next payment will automatically apply your accumulated discount: **{current_discount}% OFF!**")
    
    col_pay, col_store = st.columns(2)

    with col_pay:
        st.subheader("Manual Payment (M-Pesa)")
        st.markdown("**1. Pay KES 500 to Till Number 123456**")
        phone = st.text_input("M-Pesa Phone Number (07...)", key="mpesa_phone")
        code = st.text_input("M-Pesa Confirmation Code (e.g., QRT38D)", key="mpesa_code")
        
        if st.button("Submit Payment for Review", type="primary", use_container_width=True):
            db.add_manual_payment(st.session_state.user_id, phone, code)
            st.success("Payment submitted! An admin will approve your Premium status shortly.")

    with col_store:
        st.subheader("🛒 XP Coin Discount Store")
        st.markdown(f"You have **{xp_coins:,} XP Coins** to spend.")

        st.markdown(f"#### 5% Discount Cheque")
        st.markdown(f"Cost: **{CHEQUE_5_PERCENT_COST:,} XP Coins**")
        if st.button("Buy 5% Cheque", disabled=(xp_coins < CHEQUE_5_PERCENT_COST) or current_discount >= MAX_DISCOUNT_PERCENT, key="buy_5"):
            if db.deduct_spendable_xp(st.session_state.user_id, CHEQUE_5_PERCENT_COST):
                db.add_discount(st.session_state.user_id, 5)
                st.success("5% Discount Cheque purchased!")
                st.rerun()

        st.markdown(f"#### 20% Discount Cheque")
        st.markdown(f"Cost: **{CHEQUE_20_PERCENT_COST:,} XP Coins**")
        if st.button("Buy 20% Cheque", disabled=(xp_coins < CHEQUE_20_PERCENT_COST) or current_discount >= MAX_DISCOUNT_PERCENT, key="buy_20"):
            if db.deduct_spendable_xp(st.session_state.user_id, CHEQUE_20_PERCENT_COST):
                db.add_discount(st.session_state.user_id, 20)
                st.success("20% Discount Cheque purchased!")
                st.rerun()


def admin_dashboard(db: Database):
    st.title("👑 Admin Dashboard")
    st.warning("This tab is strictly for the Administrator account only.")
    
    pending_payments = db.get_pending_payments()
    flagged_users = db.get_flagged_for_discount()

    st.header("1. Pending Premium Payments")
    if pending_payments:
        for payment in pending_payments:
            st.expander(f"**{payment['email']}** - Code: {payment['mpesa_code']}").markdown(f"**Phone:** {payment['phone']} - **Submitted:** {payment['timestamp']}")
            col_a, col_r, _ = st.columns([1, 1, 4])
            with col_a:
                if st.button("✅ Approve", key=f"approve_{payment['id']}"):
                    db.approve_manual_payment(payment['id'])
                    st.success(f"Approved Premium for {payment['email']}.")
                    st.rerun()
            with col_r:
                if st.button("❌ Reject", key=f"reject_{payment['id']}"):
                    # Simplified reject logic
                    st.error(f"Rejected payment for {payment['email']}.")
                    st.rerun()
            st.divider()
    else:
        st.info("No pending payments to review.")

    st.header("2. Leaderboard Winners (Automatic 20% Discount)")
    if flagged_users:
        for user in flagged_users:
            discount_status = "Granted" if user['discount'] >= 20 else "Pending Approval"
            st.expander(f"**{user['name'] or user['email']}** - Status: {discount_status}").markdown(f"**Win Streak:** {user['leaderboard_win_streak']} days - **Current Discount:** {user['discount']}%")
            
            if user['discount'] < 20:
                if st.button("Apply Automatic 20% Cheque", key=f"apply_auto_{user['user_id']}"):
                    db.add_discount(user['user_id'], 20)
                    st.success(f"20% Cheque applied for {user['email']}.")
                    st.rerun()
            st.divider()
    else:
        st.info("No users currently qualify.")
        
def settings_tab(db: Database):
    st.title("🛠️ Settings")
    st.info("Account management and security settings will go here.")


# ==============================================================================
# MAIN APPLICATION FLOW
# ==============================================================================

def main():
    init_session()
    apply_theme()
    db = st.session_state.db
    
    if st.session_state.show_welcome: welcome_screen(); return
    if st.session_state.show_forgot_password: forgot_password_block(); return
    if not st.session_state.logged_in: login_block(); return
    
    # User is logged in
    sidebar(db) 
    
    tabs = ["Chat Tutor", "Progress", "Settings"]
    tier = get_user_tier(db, st.session_state.user_id)
    
    if tier in ["premium", "admin"]:
        tabs += ["PDF Q&A", "Exam Prep", "Essay Grader"]
    if tier == "basic":
        tabs.append("Premium")
    if tier == "admin":
        tabs.append("Admin")

    tab_map = {
        "Chat Tutor": chat_tab, "Progress": progress_tab, "Settings": settings_tab,
        "PDF Q&A": pdf_tab, "Exam Prep": exam_tab, "Essay Grader": essay_tab,
        "Premium": premium_tab, "Admin": admin_dashboard
    }
    
    tab_objs = st.tabs(tabs)
    
    for name, obj in zip(tabs, tab_objs):
        with obj:
            st.session_state.current_tab = name
            enforce_access(db) 
            tab_map[name](db)

if __name__ == '__main__':
    main()
