# app.py
import streamlit as st
import time
import bcrypt
import pyotp
import qrcode
from io import BytesIO
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, BADGES

st.set_page_config(page_title="LearnFlow AI", layout="wide")
st.markdown(
    "<style>#MainMenu,footer,header{visibility:hidden;}</style>", unsafe_allow_html=True
)

# ----------------------------------------------------------------------
# INIT
# ----------------------------------------------------------------------
@st.cache_resource
def get_db():
    return Database()


@st.cache_resource
def get_ai():
    key = st.secrets.get("GEMINI_API_KEY", "")
    if not key:
        st.error("Add GEMINI_API_KEY to .streamlit/secrets.toml")
        st.stop()
    return AIEngine(key)


db = get_db()
ai = get_ai()


# ----------------------------------------------------------------------
# SETTINGS (font, theme, language, 2FA)
# ----------------------------------------------------------------------
def apply_settings():
    font = st.session_state.get("font_size", 16)
    theme = st.session_state.get("theme", "light")
    css = f"""
    <style>
    .stApp {{font-size:{font}px;}}
    .stApp {{background:{'#fff' if theme=='light' else '#1e1e1e'};color:{'#000' if theme=='light' else '#fff'};}}
    .stTextInput > div > div > input {{background:{'#f0f0f0' if theme=='light' else '#333'};color:{'#000' if theme=='light' else '#fff'};}}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# ----------------------------------------------------------------------
# WELCOME PAGE
# ----------------------------------------------------------------------
def welcome():
    st.markdown(
        """
        <div style='text-align:center;padding:100px;'>
            <h1 style='font-size:70px;background:-webkit-linear-gradient(#00d4b1,#00ffaa);
                       -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                       animation:glow 2s infinite alternate;'>
                LearnFlow AI
            </h1>
            <p style='font-size:24px;color:#aaa;'>Kenya's #1 AI Tutor</p>
            <br><br>
            <button onclick="document.getElementById('go').click()"
                    style='padding:16px 60px;font-size:22px;background:#00d4b1;color:black;
                           border:none;border-radius:50px;cursor:pointer;'>
                Continue
            </button>
        </div>
        <style>@keyframes glow{from{text-shadow:0 0 20px #00d4b1}to{text-shadow:0 0 40px #00ffcc}}</style>
        """,
        unsafe_allow_html=True,
    )
    if st.button("Continue", key="go", use_container_width=True):
        st.session_state.page = "auth"
        st.rerun()


# ----------------------------------------------------------------------
# AUTH (Login / Sign-up)
# ----------------------------------------------------------------------
def auth():
    st.markdown("<h1 style='text-align:center;color:#00d4b1;'>Welcome Back!</h1>", unsafe_allow_html=True)
    login_tab, signup_tab = st.tabs(["Login", "Sign Up"])

    # ---------- LOGIN ----------
    with login_tab:
        with st.form("login_form"):
            email = st.text_input("Email")
            pwd = st.text_input("Password", type="password")
            totp = st.text_input("2FA Code (if enabled)")
            if st.form_submit_button("Login"):
                ok, msg = login_user(email.lower(), pwd, totp)
                if ok:
                    st.success("Logged in!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(msg)

    # ---------- SIGN-UP ----------
    with signup_tab:
        with st.form("signup_form"):
            name = st.text_input("Name")
            email = st.text_input("Email")
            pwd = st.text_input("Password", type="password")
            phone = st.text_input("Phone")
            if st.form_submit_button("Create Account"):
                if db.get_user_by_email(email.lower()):
                    st.error("Email already exists")
                else:
                    db.create_user(name, email.lower(), pwd, phone)
                    st.success("Account created! Please log in.")
                    st.balloons()


# ----------------------------------------------------------------------
# LOGIN LOGIC
# ----------------------------------------------------------------------
def login_user(email: str, password: str, totp_code: str = ""):
    user = db.get_user_by_email(email)
    if not user:
        return False, "User not found"

    stored = user["password_hash"]
    if isinstance(stored, str):
        stored = stored.encode("utf-8")
    if not bcrypt.checkpw(password.encode(), stored):
        return False, "Wrong password"

    # 2FA check
    if user.get("two_fa_secret"):
        if not totp_code or not pyotp.TOTP(user["two_fa_secret"]).verify(totp_code):
            return False, "Invalid 2FA code"

    st.session_state.update(
        {
            "logged_in": True,
            "user_id": user["user_id"],
            "user_name": user.get("name", "Student"),
            "user_email": email,
            "is_admin": user["role"] == "admin",
            "is_premium": bool(user["is_premium"]),
        }
    )
    try:
        db.log_activity(user["user_id"], "login")
    except:
        pass
    return True, ""


# ----------------------------------------------------------------------
# ADMIN CONTROL CENTER (full page)
# ----------------------------------------------------------------------
def admin_control_center():
    st.markdown("# ADMIN CONTROL CENTER")
    st.success("Welcome KingMumo!")

    tab1, tab2, tab3, tab4 = st.tabs(
        ["Pending Payments", "All Users", "Revenue", "Leaderboard & Badges"]
    )

    # ---- Pending Payments (show M-Pesa ref + phone) ----
    with tab1:
        payments = db.get_pending_payments()
        if not payments:
            st.info("No pending payments")
        else:
            for p in payments:
                with st.expander(f"{p['name']} – {p['phone']} – KSh 500"):
                    st.write(f"**M-Pesa Code:** `{p['mpesa_code']}`")
                    st.write(f"**Phone:** {p['phone']}")
                    c1, c2 = st.columns(2)
                    if c1.button("APPROVE", key=f"app_{p['id']}"):
                        db.approve_payment(p["id"])
                        st.success("Premium activated!")
                        st.rerun()
                    if c2.button("Reject", key=f"rej_{p['id']}"):
                        db.reject_payment(p["id"])
                        st.error("Rejected")
                        st.rerun()

    # ---- All Users ----
    with tab2:
        users = db.get_all_users()
        st.dataframe(
            [
                {
                    "Name": u["name"],
                    "Email": u["email"],
                    "Role": u["role"],
                    "Premium": "Yes" if u["is_premium"] else "No",
                }
                for u in users
            ],
            use_container_width=True,
        )

    # ---- Revenue ----
    with tab3:
        total = db.get_revenue()
        st.metric("Total Revenue", f"KSh {total}")
        # placeholder chart – replace with real data if you have it
        st.bar_chart({"Jan": 0, "Feb": 0, "Mar": total})

    # ---- Leaderboard + Badges ----
    with tab4:
        st.markdown("### Leaderboard (Quiz Scores)")
        board = db.get_leaderboard(20)
        for i, entry in enumerate(board):
            st.write(
                f"**#{i+1}** {entry['name']} — {entry['total_score']} pts ({entry['quizzes']} quizzes)"
            )

        st.markdown("### All User Badges")
        for u in db.get_all_users():
            ub = db.get_user_badges(u["user_id"])
            if ub:
                badges_str = ", ".join([BADGES.get(b, b) for b in ub])
                st.write(f"**{u['name']}**: {badges_str}")


# ----------------------------------------------------------------------
# SETTINGS PAGE (font, theme, language, 2FA)
# ----------------------------------------------------------------------
def settings_page():
    st.title("Settings")
    with st.form("settings_form"):
        st.session_state.font_size = st.slider(
            "Font Size", 12, 24, st.session_state.get("font_size", 16)
        )
        st.session_state.theme = st.selectbox(
            "Theme",
            ["light", "dark"],
            index=0 if st.session_state.get("theme", "light") == "light" else 1,
        )
        st.session_state.lang = st.selectbox(
            "Language", ["English", "Kiswahili"], index=0
        )

        # ---- 2FA toggle ----
        user = db.get_user_by_email(st.session_state.user_email)
        has_2fa = bool(user.get("two_fa_secret"))
        enable_2fa = st.checkbox("Enable 2-Factor Authentication", value=has_2fa)

        qr_img = None
        if enable_2fa and not has_2fa:
            secret = pyotp.random_base32()
            totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
                name=st.session_state.user_email, issuer_name="LearnFlow AI"
            )
            qr = qrcode.make(totp_uri)
            buf = BytesIO()
            qr.save(buf, format="PNG")
            qr_img = buf.getvalue()
            st.session_state._new_2fa_secret = secret

        if qr_img:
            st.image(qr_img, caption="Scan with Authenticator app")
            st.info("After scanning, click **Save Settings** to activate 2FA.")

        if st.form_submit_button("Save Settings"):
            # Save basic settings
            st.success("Settings saved!")
            # 2FA handling
            if enable_2fa and not has_2fa:
                db.enable_2fa(st.session_state.user_id, st.session_state._new_2fa_secret)
                del st.session_state._new_2fa_secret
            elif not enable_2fa and has_2fa:
                db.disable_2fa(st.session_state.user_id)
            time.sleep(1)
            st.rerun()


# ----------------------------------------------------------------------
# MAIN APP (Dashboard + Admin extras)
# ----------------------------------------------------------------------
def main_app():
    apply_settings()

    # ---- Sidebar ----
    st.sidebar.success(f"Welcome {st.session_state.user_name}!")

    # Common buttons
    if st.sidebar.button("My Account"):
        st.session_state.page = "dashboard"
    if st.sidebar.button("Settings"):
        st.session_state.page = "settings"
    if st.sidebar.button("Logout"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    # Admin only
    if st.session_state.is_admin:
        if st.sidebar.button("Control Center"):
            st.session_state.page = "admin_center"

    # ---- Page routing ----
    if st.session_state.get("page") == "admin_center":
        admin_control_center()
        return
    if st.session_state.get("page") == "settings":
        settings_page()
        return

    # ---- Default Dashboard (same for premium & admin) ----
    st.title("My Dashboard")
    if st.session_state.is_admin:
        st.success("**Unlimited AI access** – no monthly limits.")
    elif st.session_state.is_premium:
        st.info("Premium user – enjoy higher quotas.")
    else:
        st.warning("Upgrade to Premium for more features!")

    # Leaderboard (top 5) & own badges
    st.markdown("### Leaderboard")
    board = db.get_leaderboard(5)
    for i, e in enumerate(board):
        st.write(f"**#{i+1}** {e['name']} — {e['total_score']} pts")

    my_badges = db.get_user_badges(st.session_state.user_id)
    if my_badges:
        st.markdown("### My Badges")
        st.write(", ".join([BADGES.get(b, b) for b in my_badges]))

    # Subject selector + chat/quiz toggle
    subject = st.sidebar.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))
    mode = st.sidebar.radio("Mode", ["Chat", "Quiz"], horizontal=True)
    if mode == "Quiz":
        show_quiz_mode(subject)
    else:
        show_chat_mode(subject)


# ----------------------------------------------------------------------
# CHAT MODE
# ----------------------------------------------------------------------
def show_chat_mode(subject):
    st.header(subject)
    prompt = st.chat_input("Ask me anything...")
    if prompt:
        with st.chat_message("user"):
            st.write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                resp = ai.generate_response(
                    f"{SUBJECT_PROMPTS[subject]}\nStudent: {prompt}",
                    SUBJECT_PROMPTS[subject],
                )
            st.write(resp)


# ----------------------------------------------------------------------
# QUIZ MODE
# ----------------------------------------------------------------------
def show_quiz_mode(subject):
    st.header(f"Quiz – {subject}")
    if st.button("Start 5-Question Quiz"):
        questions = ai.generate_mcq_questions(subject, 5)
        st.session_state.quiz = {
            "questions": questions,
            "answers": {},
            "start": time.time(),
        }
        st.rerun()

    if "quiz" in st.session_state:
        q = st.session_state.quiz
        for i, ques in enumerate(q["questions"]):
            with st.expander(f"Q{i+1}: {ques['question']}"):
                ans = st.radio("Choose", ques["options"], key=f"q{i}")
                q["answers"][i] = ans

        if st.button("Submit Quiz"):
            result = ai.grade_mcq(q["questions"], q["answers"])
            db.record_quiz_score(
                st.session_state.user_id, subject, result["correct"], result["total"]
            )
            # Badges
            db.unlock_badge(st.session_state.user_id, "first_quiz")
            if result["percentage"] == 100:
                db.unlock_badge(st.session_state.user_id, "perfect_score")

            st.success(
                f"Score: {result['correct']}/{result['total']} ({result['percentage']}%)"
            )
            for r in result["results"]:
                st.write(f"**Q:** {r['question']}")
                st.write(
                    f"Your: {r['user_answer']} | Correct: {r['correct_answer']}"
                )
                if not r["is_correct"]:
                    st.info(r["feedback"])

            del st.session_state.quiz
            st.rerun()


# ----------------------------------------------------------------------
# ROUTER
# ----------------------------------------------------------------------
if "page" not in st.session_state:
    st.session_state.page = "welcome"

if st.session_state.page == "welcome":
    welcome()
elif st.session_state.page == "auth":
    auth()
elif st.session_state.get("logged_in"):
    main_app()
else:
    st.session_state.page = "auth"
    st.rerun()
