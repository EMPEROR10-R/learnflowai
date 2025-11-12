# app.py
import streamlit as st
import pyotp, qrcode, bcrypt, json
from io import BytesIO
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="LearnFlow AI", page_icon="🇰🇪", layout="wide")
st.markdown("""
<style>
    .main-header {font-size:2.8rem; font-weight:bold;
        background:linear-gradient(135deg,#009E60,#FFD700,#CE1126);
        -webkit-background-clip:text; -webkit-text-fill-color:transparent;
        text-align:center;}
    .welcome-box {background:linear-gradient(135deg,#009E60,#FFD700);
        padding:50px; border-radius:20px; color:white; text-align:center;}
    .streak-badge {background:linear-gradient(135deg,#FF6B6B,#FFE66D);
        padding:6px 14px; border-radius:20px; color:white; font-weight:bold;}
    .premium-badge {background:#FFD700; color:#000; padding:4px 10px; border-radius:12px; font-weight:bold;}
    .leaderboard {background:#f0f8ff; padding:20px; border-radius:10px;}
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_db():
    try:
        db = Database()
        return db
    except Exception as e:
        st.error("Database connection failed. Check logs.")
        print(f"DB Init Error: {e}")
        class DummyDB:
            def get_user_by_email(self, email): return None
            def create_user(self, email, pwd): return None
            def update_user_activity(self, user_id): pass
            def is_2fa_enabled(self, user_id): return False
            def verify_2fa_code(self, user_id, code): return True
            def check_premium(self, user_id): return False
            def update_streak(self, user_id): return 1
            def add_chat_history(self, *args): pass
            def get_user(self, user_id): return {"total_queries": 0, "streak_days": 1, "badges": "[]", "profile_pic": None, "theme": "light"}
            def get_children(self, user_id): return []
            def link_parent(self, *args): return "Error"
            def generate_2fa_secret(self, user_id): return "SECRET123"
            def disable_2fa(self, user_id): pass
            def add_manual_payment(self, *args): pass
            def get_pending_manual_payments(self): return []
            def approve_manual_payment(self, id): pass
            def reject_manual_payment(self, id): pass
            def get_all_users(self): return []
            def add_score(self, *args): pass
            def get_leaderboard(self, category): return []
            def add_badge(self, *args): pass
            def toggle_premium(self, *args): pass
            def revoke_user(self, *args): pass
            def update_settings(self, *args): pass
        return DummyDB()

@st.cache_resource
def init_ai():
    # Placeholder for secrets handling
    class Secrets:
        def get(self, key): return "DUMMY_KEY" 
    try:
        k = st.secrets.get("GEMINI_API_KEY")
    except:
        k = Secrets().get("GEMINI_API_KEY")
        
    if not k: 
        pass 
    return AIEngine(k)

# Initialize DB and AI engine
db = init_db()

try:
    ai_engine = init_ai()
except:
    pass

def init_session():
    defaults = {
        "logged_in": False, "user_id": None, "is_admin": False, "user": None,
        "show_welcome": True, "chat_history": [], "current_subject": "Mathematics",
        "is_parent": False, "theme": "light", "brightness": 100, "font": "sans-serif"
    }
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

def apply_theme():
    if st.session_state.theme == "dark":
        st.markdown("<style>body {background-color: #333; color: #fff;}</style>", unsafe_allow_html=True)
    # Add more theme logic as needed

def qr_image(email, secret):
    uri = pyotp.TOTP(secret).provisioning_uri(email, "LearnFlow AI")
    qr = qrcode.make(uri)
    buf = BytesIO()
    qr.save(buf, "PNG")
    return buf.getvalue()

def login_user(email, pwd, totp=""):
    if not email or "@" not in email:
        return False, "Enter a valid email.", None
    user = db.get_user_by_email(email)
    if not user or not bcrypt.checkpw(pwd.encode(), user["password_hash"].encode()):
        return False, "Invalid email or password.", None
    if db.is_2fa_enabled(user["user_id"]) and not db.verify_2fa_code(user["user_id"], totp):
        return False, "Invalid 2FA code.", None
    db.update_user_activity(user["user_id"])
    return True, "Login successful!", user

def welcome_screen():
    st.markdown('<div class="welcome-box"><h1>LearnFlow AI</h1><p>Your Kenyan AI Tutor</p><p>KCPE • KPSEA • KJSEA • KCSE</p></div>', unsafe_allow_html=True)
    _, col, _ = st.columns([1,1,1])
    with col:
        if st.button("Start Learning!", type="primary", use_container_width=True):
            st.session_state.show_welcome = False
            st.rerun()

def login_block():
    if st.session_state.logged_in: return
    st.markdown("### Login or Sign Up")
    choice = st.radio("Action", ["Login", "Sign Up"], horizontal=True)
    email = st.text_input("Email", key=f"{choice.lower()}_email")
    pwd = st.text_input("Password", type="password", key=f"{choice.lower()}_pwd")
    totp = st.text_input("2FA Code (if enabled)", key="totp") if choice == "Login" else ""

    if st.button(choice):
        if not email or "@" not in email:
            st.error("Please enter a valid email.")
        elif len(pwd) < 6:
            st.error("Password must be 6+ characters.")
        elif choice == "Sign Up":
            if db.create_user(email, pwd):
                st.success("Account created! Now log in.")
            else:
                st.error("Email already in use.")
        else:
            ok, msg, u = login_user(email, pwd, totp)
            st.write(msg)
            if ok:
                st.session_state.update({
                    "logged_in": True, "user_id": u["user_id"],
                    "is_admin": u["role"] == "admin", "user": u,
                    "is_parent": bool(u.get("parent_id"))
                })
                st.rerun()
    st.stop()

def sidebar():
    with st.sidebar:
        st.markdown("## LearnFlow AI")
        if st.session_state.user_id and db.check_premium(st.session_state.user_id):
            st.markdown('<span class="premium-badge">PREMIUM</span>', unsafe_allow_html=True)
        streak = db.update_streak(st.session_state.user_id)
        st.markdown(f'<span class="streak-badge">Streak: {streak} days</span>', unsafe_allow_html=True)
        st.session_state.current_subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))
        if st.button("Logout"):
            for k in st.session_state.keys(): del st.session_state[k]
            st.rerun()

# === TABS ===
def chat_tab():
    st.markdown(f"### {st.session_state.current_subject} Tutor")
    for m in st.session_state.chat_history:
        role = "You" if m["role"] == "user" else "AI"
        st.markdown(f"**{role}:** {m['content']}")
    q = st.text_area("Ask:", height=100)
    if st.button("Send") and q:
        st.session_state.chat_history.append({"role":"user","content":q})
        with st.spinner("Thinking…"):
            resp = ai_engine.generate_response(q, get_enhanced_prompt(st.session_state.current_subject, q, ""))
        st.session_state.chat_history.append({"role":"assistant","content":resp})
        db.add_chat_history(st.session_state.user_id, st.session_state.current_subject, q, resp)
        db.add_score(st.session_state.user_id, "chat", 1)  # Simple point for activity
        st.rerun()

def pdf_tab():
    st.markdown("### PDF Upload & Analysis")
    uploaded = st.file_uploader("Upload PDF", type="pdf")
    if uploaded:
        txt = ai_engine.extract_text_from_pdf(uploaded.read()) 
        st.success(f"Extracted {len(txt)} characters")
        q = st.text_area("Ask about this PDF")
        if st.button("Ask") and q:
            resp = ai_engine.generate_response(f"Document:\n{txt[:4000]}\n\nQuestion: {q[:1000]}", "Answer in 1-2 sentences.")
            st.markdown(f"**AI:** {resp}")
            db.add_badge(st.session_state.user_id, "pdf_explorer")

def progress_tab():
    user = db.get_user(st.session_state.user_id)
    user_data = user if user else {"total_queries": 0, "streak_days": 0, "badges": "[]"}
    c1,c2,c3 = st.columns(3)
    c1.metric("Queries", user_data.get("total_queries", 0))
    c2.metric("Streak", f"{user_data.get('streak_days', 0)} days")
    badges = json.loads(user_data.get("badges", "[]"))
    c3.metric("Badges", len(badges))
    st.markdown("### Your Badges")
    for b in badges:
        st.write(f"- {BADGES.get(b, b)}")

    # Leaderboards
    st.markdown("### Leaderboards")
    exam_lb = db.get_leaderboard("exam")
    essay_lb = db.get_leaderboard("essay")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="leaderboard">**Exam Prep Leaderboard**</div>', unsafe_allow_html=True)
        if exam_lb:
            st.dataframe(pd.DataFrame(exam_lb))
        else:
            st.info("No scores yet.")
    with col2:
        st.markdown('<div class="leaderboard">**Essay Grader Leaderboard**</div>', unsafe_allow_html=True)
        if essay_lb:
            st.dataframe(pd.DataFrame(essay_lb))
        else:
            st.info("No scores yet.")

    # Monthly discount check
    if datetime.now().day == 1:  # Simulate end of month
        leaders = db.get_monthly_leaders()
        for leader_id, category in leaders:
            db.apply_discount(leader_id, 0.10)  # 10% discount

def exam_tab():
    st.markdown("### Exam Prep")
    exam = st.selectbox("Exam", list(EXAM_TYPES.keys()))
    subj = st.selectbox("Subject", EXAM_TYPES[exam]["subjects"])
    n = st.slider("Questions", 1, 10, 5)
    if st.button("Generate"):
        with st.spinner("Generating…"):
            questions = ai_engine.generate_mcq_questions(subj, n)
        st.session_state.exam_questions = questions
        st.session_state.user_answers = {}
        st.rerun()

    if "exam_questions" in st.session_state:
        questions = st.session_state.exam_questions
        for i, q in enumerate(questions):
            st.markdown(f"**Q{i+1}:** {q['question']}")
            opts = q['options']
            st.session_state.user_answers[i] = st.radio(f"Options {i+1}", opts, key=f"q{i}")

        if st.button("Submit Answers"):
            with st.spinner("Grading…"):
                result = ai_engine.grade_mcq(questions, st.session_state.user_answers)
                score = result['percentage']
                db.add_score(st.session_state.user_id, "exam", score)
                if score == 100:
                    db.add_badge(st.session_state.user_id, "perfect_score")
                st.markdown(f"**Your Score:** {score}% ({result['correct']}/{result['total']})")
                for res in result['results']:
                    st.markdown(f"- {res['question']}: Your answer {res['user_answer']} | Correct: {res['correct_answer']} | {res['feedback']}")
            del st.session_state.exam_questions
            del st.session_state.user_answers

def essay_tab():
    st.markdown("### Essay Grader")
    essay = st.text_area("Paste essay", height=200)
    rubric = st.text_area("Rubric (optional)", value="Grade on structure, grammar, content relevance to Kenyan curriculum.")
    if st.button("Grade") and essay:
        with st.spinner("Grading…"):
            result = ai_engine.grade_essay(essay, rubric)
            score = result['score']
            db.add_score(st.session_state.user_id, "essay", score)
            if score >= 90:
                db.add_badge(st.session_state.user_id, "quiz_ace")
            st.markdown(f"**Score:** {score}/100 – {result['feedback']}")

def premium_tab():
    st.markdown("### Upgrade to Premium – KES 500/month")
    phone = st.text_input("M-Pesa Phone")
    code = st.text_input("Transaction Code")
    if st.button("Submit Proof"):
        db.add_manual_payment(st.session_state.user_id, phone, code)
        st.success("Submitted! Admin will review.")

def settings_tab():
    st.header("Settings")
    st.subheader("Two-Factor Authentication")
    if st.session_state.user_id and db.is_2fa_enabled(st.session_state.user_id):
        st.success("2FA Enabled")
        if st.button("Disable 2FA"):
            db.disable_2fa(st.session_state.user_id)
            st.success("2FA disabled.")
            st.rerun()
    else:
        st.info("Enable 2FA (free with Google Authenticator)")
        if st.button("Enable 2FA") and st.session_state.user:
            secret = db.generate_2fa_secret(st.session_state.user["email"])
            st.image(qr_image(st.session_state.user["email"], secret), caption="Scan with Authenticator")
            st.code(secret)
    if not st.session_state.is_parent and not st.session_state.is_admin and st.session_state.user_id:
        st.subheader("Link Parent")
        p_email = st.text_input("Parent Email")
        p_pass = st.text_input("Parent Password", type="password")
        if st.button("Link Parent"):
            msg = db.link_parent(st.session_state.user_id, p_email, p_pass)
            st.write(msg)

    # New Settings
    st.subheader("Appearance")
    theme = st.selectbox("Theme", ["light", "dark"], index=0 if st.session_state.theme == "light" else 1)
    brightness = st.slider("Brightness", 50, 100, st.session_state.brightness)
    font = st.selectbox("Font", ["sans-serif", "serif", "monospace"])
    profile_pic = st.file_uploader("Upload Profile Pic", type=["jpg", "png"])
    if st.button("Save Settings"):
        settings = {"theme": theme, "brightness": brightness, "font": font}
        if profile_pic:
            settings["profile_pic"] = profile_pic.read()  # Store bytes in DB
        db.update_settings(st.session_state.user_id, settings)
        st.session_state.theme = theme
        st.session_state.brightness = brightness
        st.session_state.font = font
        apply_theme()
        st.success("Settings saved!")

def parent_dashboard():
    st.header("Parent Dashboard")
    children = db.get_children(st.session_state.user_id)
    if not children:
        st.info("No children linked.")
        return
    for child in children:
        with st.expander(f"**{child.get('name') or child['email']}**"):
            st.write("Activity tracking coming soon…")

def admin_dashboard():
    if not st.session_state.is_admin:
        st.error("Access denied.")
        return
    st.markdown("## Admin Dashboard")
    users = db.get_all_users()
    if users:
        user_list = [dict(u) if not isinstance(u, dict) else u for u in users]
        df = pd.DataFrame(user_list)
        if "created_at" in df.columns:
            df["created_at"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d")
        st.dataframe(df, use_container_width=True)

    # User Management
    st.subheader("User Management")
    user_id = st.text_input("User ID to Manage")
    if user_id:
        if st.button("Add to Premium"):
            db.toggle_premium(user_id, True)
            st.success("Added to Premium.")
        if st.button("Revoke Premium"):
            db.toggle_premium(user_id, False)
            st.success("Revoked Premium.")
        if st.button("Revoke Qualifications/Badges"):
            db.revoke_user(user_id)
            st.success("Revoked qualifications.")

    st.markdown("### Pending Manual Payments")
    pending = db.get_pending_manual_payments()
    if pending:
        for p in pending:
            p_dict = dict(p) if not isinstance(p, dict) else p
            c1,c2,c3 = st.columns([4,1,1])
            with c1:
                st.write(f"**{p_dict.get('name') or p_dict.get('email', 'Unknown User')}**")
                st.caption(f"Phone: {p_dict.get('phone')} | Code: `{p_dict.get('mpesa_code')}`")
            with c2:
                if st.button("Approve", key=f"app_{p_dict['id']}"):
                    db.approve_manual_payment(p_dict["id"])
                    st.success("Approved!")
                    st.rerun()
            with c3:
                if st.button("Reject", key=f"rej_{p_dict['id']}"):
                    db.reject_manual_payment(p_dict["id"])
                    st.rerun()
    else:
        st.info("No pending requests.")

def main():
    init_session()
    apply_theme()
    if st.session_state.show_welcome:
        welcome_screen()
        return
    login_block()
    sidebar()

    tabs = ["Chat Tutor","PDF Upload","Progress","Exam Prep","Essay Grader","Settings"]
    if not st.session_state.is_admin:
        tabs.insert(5, "Premium")
    if st.session_state.is_parent: tabs.append("Parent Dashboard")
    if st.session_state.is_admin: tabs.append("Admin Dashboard")
    tab_objs = st.tabs(tabs)

    # Static Tabs
    if len(tab_objs) > 0: 
        with tab_objs[0]: chat_tab()
    if len(tab_objs) > 1: 
        with tab_objs[1]: pdf_tab()
    if len(tab_objs) > 2: 
        with tab_objs[2]: progress_tab()
    if len(tab_objs) > 3: 
        with tab_objs[3]: exam_tab()
    if len(tab_objs) > 4: 
        with tab_objs[4]: essay_tab()
    if "Premium" in tabs:
        premium_index = tabs.index("Premium")
        with tab_objs[premium_index]: premium_tab()
    if len(tab_objs) > 5: 
        with tab_objs[5 if "Premium" not in tabs else 6]: settings_tab()
    
    # Dynamic Tabs
    if st.session_state.is_parent and "Parent Dashboard" in tabs:
        parent_index = tabs.index("Parent Dashboard")
        if parent_index < len(tab_objs):
            with tab_objs[parent_index]: parent_dashboard()
        
    if st.session_state.is_admin and "Admin Dashboard" in tabs:
        admin_index = tabs.index("Admin Dashboard")
        if admin_index < len(tab_objs):
            with tab_objs[admin_index]: admin_dashboard()


if __name__ == "__main__":
    main()
