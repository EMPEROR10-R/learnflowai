# app.py (debugged)
import streamlit as st
import time
import bcrypt
import pyotp
import qrcode
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, BADGES
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

# =============================================
# 1. PAGE CONFIG & HIDE BRANDING
# =============================================
st.set_page_config(page_title="LearnFlow AI", layout="wide", menu_items=None)
st.markdown("""
<style>
    #MainMenu, header, footer {visibility: hidden !important;}
    .stApp > div:last-child {display: none !important;}
    .block-container {padding-top: 2rem;}
</style>
""", unsafe_allow_html=True)

# =============================================
# 2. SAFE INIT
# =============================================
@st.cache_resource
def get_db():
    try:
        return Database()
    except Exception as e:
        st.error("Database failed. Run `python fix_db.py` first.")
        st.code(str(e))
        st.stop()

@st.cache_resource
def get_ai():
    key = st.secrets.get("GEMINI_API_KEY", "")
    if not key:
        st.error("GEMINI_API_KEY missing!")
        st.info("Add it in Streamlit Cloud → Settings → Secrets")
        st.stop()
    try:
        return AIEngine(key)
    except Exception as e:
        st.error("AI Engine failed.")
        st.code(str(e))
        st.stop()

db = get_db()
ai = get_ai()

# =============================================
# 3. APPLY SETTINGS
# =============================================
def apply_settings():
    font = st.session_state.get("font_size", 16)
    theme = st.session_state.get("theme", "light")
    st.markdown(f"""
    <style>
    .stApp {{font-size:{font}px;}}
    .stApp {{background:{'#fff' if theme=='light' else '#1e1e1e'};color:{'#000' if theme=='light' else '#fff'};}}
    .stTextInput > div > div > input {{background:{'#f0f0f0' if theme=='light' else '#333'};color:{'#000' if theme=='light' else '#fff'};}}
    </style>
    """, unsafe_allow_html=True)

# =============================================
# 4. WELCOME PAGE
# =============================================
def welcome():
    st.markdown("""
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
    """, unsafe_allow_html=True)
    if st.button("Continue", key="go", use_container_width=True):
        st.session_state.page = "auth"
        st.experimental_rerun()

# =============================================
# 5. AUTH PAGE
# =============================================
def auth():
    st.markdown("<h1 style='text-align:center;color:#00d4b1;'>Welcome Back!</h1>", unsafe_allow_html=True)
    login_tab, signup_tab = st.tabs(["Login", "Sign Up"])

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
                    st.experimental_rerun()
                else:
                    st.error(msg)

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

# =============================================
# 6. LOGIN LOGIC
# =============================================
def login_user(email: str, password: str, totp_code: str = ""):
    user = db.get_user_by_email(email)
    if not user:
        return False, "User not found"

    stored = user["password_hash"]
    if isinstance(stored, str):
        stored = stored.encode()
    if not bcrypt.checkpw(password.encode(), stored):
        return False, "Wrong password"

    if user.get("two_fa_secret"):
        if not totp_code or not pyotp.TOTP(user["two_fa_secret"]).verify(totp_code):
            return False, "Invalid 2FA code"

    st.session_state.update({
        "logged_in": True,
        "user_id": user["user_id"],
        "user_name": user.get("name", "Student"),
        "user_email": email,
        "is_admin": user["role"] == "admin",
        "is_premium": bool(user.get("is_premium")),
    })
    try:
        db.log_activity(user["user_id"], "login")
    except:
        pass
    return True, ""

# =============================================
# 7. ADMIN CONTROL CENTER
# =============================================
def admin_control_center():
    st.markdown("# ADMIN CONTROL CENTER")
    st.success("Welcome KingMumo!")

    t1, t2, t3, t4 = st.tabs(["Pending Payments", "All Users", "Revenue", "Leaderboard & Badges"])

    with t1:
        payments = db.get_pending_payments()
        if not payments:
            st.info("No pending payments")
        else:
            for p in payments:
                with st.expander(f"{p.get('name','Unknown')} – {p.get('phone','-')} – KSh 500"):
                    st.write(f"**M-Pesa Code:** `{p.get('mpesa_code','-')}`")
                    st.write(f"**Phone:** {p.get('phone','-')}")
                    c1, c2 = st.columns(2)
                    if c1.button("APPROVE", key=f"app_{p['id']}"):
                        db.approve_payment(p["id"])
                        st.success("Premium activated!")
                        st.experimental_rerun()
                    if c2.button("Reject", key=f"rej_{p['id']}"):
                        db.reject_payment(p["id"])
                        st.error("Rejected")
                        st.experimental_rerun()

    with t2:
        users = db.get_all_users()
        st.dataframe([
            {"Name": u["name"], "Email": u["email"], "Role": u["role"], "Premium": "Yes" if u["is_premium"] else "No"}
            for u in users
        ], use_container_width=True)

    with t3:
        total = db.get_revenue()
        st.metric("Total Revenue", f"KSh {total}")

    with t4:
        st.markdown("### Leaderboard")
        board = db.get_leaderboard(20)
        for i, e in enumerate(board):
            st.write(f"**#{i+1}** {e['name']} — {e['total_score']} pts ({e['quizzes']} quizzes)")

        st.markdown("### All User Badges")
        for u in db.get_all_users():
            ub = db.get_user_badges(u["user_id"])
            if ub:
                st.write(f"**{u['name']}**: {', '.join([BADGES.get(b,b) for b in ub])}")

# =============================================
# 8. SETTINGS PAGE (2FA + Theme)
# =============================================
def settings_page():
    st.title("Settings")
    with st.form("settings_form"):
        st.session_state.font_size = st.slider("Font Size", 12, 24, st.session_state.get("font_size", 16))
        st.session_state.theme = st.selectbox("Theme", ["light", "dark"], index=0 if st.session_state.get("theme", "light") == "light" else 1)
        st.session_state.lang = st.selectbox("Language", ["English", "Kiswahili"], index=0)

        # Fetch fresh user details
        user = db.get_user_by_email(st.session_state.user_email) if st.session_state.get("user_email") else {}
        has_2fa = bool(user.get("two_fa_secret")) if user else False
        enable_2fa = st.checkbox("Enable 2-Factor Authentication", value=has_2fa)

        qr_img = None
        if enable_2fa and not has_2fa:
            secret = pyotp.random_base32()
            uri = pyotp.totp.TOTP(secret).provisioning_uri(name=st.session_state.user_email, issuer_name="LearnFlow AI")
            qr = qrcode.make(uri)
            buf = BytesIO()
            qr.save(buf, format="PNG")
            buf.seek(0)
            qr_img = buf.getvalue()
            st.session_state._new_2fa_secret = secret

        if qr_img:
            st.image(qr_img, caption="Scan with Authenticator App")
            st.info("Click **Save Settings** to activate 2FA.")

        if st.form_submit_button("Save Settings"):
            # Persist settings
            if enable_2fa and not has_2fa:
                # save secret directly using db connection
                conn = db.get_conn()
                c = conn.cursor()
                c.execute("UPDATE users SET two_fa_secret = ? WHERE user_id = ?", (st.session_state._new_2fa_secret, st.session_state.user_id))
                conn.commit()
                conn.close()
                st.session_state.pop("_new_2fa_secret", None)
            elif not enable_2fa and has_2fa:
                conn = db.get_conn()
                c = conn.cursor()
                c.execute("UPDATE users SET two_fa_secret = NULL WHERE user_id = ?", (st.session_state.user_id,))
                conn.commit()
                conn.close()
            st.success("Settings saved!")
            time.sleep(1)
            st.experimental_rerun()

# =============================================
# 9. MAIN APP (Dashboard)
# =============================================
def safe_clear_session():
    # safely clear session_state keys
    for k in list(st.session_state.keys()):
        try:
            del st.session_state[k]
        except Exception:
            pass

def main_app():
    apply_settings()

    # Sidebar
    st.sidebar.success(f"Welcome {st.session_state.get('user_name','User')}!")

    if st.sidebar.button("My Account"):
        st.session_state.page = "dashboard"
    if st.sidebar.button("Settings"):
        st.session_state.page = "settings"
    if st.sidebar.button("Logout"):
        safe_clear_session()
        st.session_state.page = "auth"
        st.experimental_rerun()

    # Admin-only Control Center button (visible only to admin)
    if st.session_state.get("is_admin"):
        if st.sidebar.button("Control Center"):
            st.session_state.page = "admin_center"

    # Routing
    if st.session_state.get("page") == "admin_center":
        # only admin can access
        if st.session_state.get("is_admin"):
            admin_control_center()
        else:
            st.warning("Access denied.")
            st.session_state.page = "dashboard"
            st.experimental_rerun()
        return

    if st.session_state.get("page") == "settings":
        settings_page()
        return

    # Dashboard
    st.title("My Dashboard")
    if st.session_state.get("is_admin"):
        st.success("**Unlimited AI Access** – No Limits")
    elif st.session_state.get("is_premium"):
        st.info("Premium User – Higher Quotas")
    else:
        st.warning("Upgrade to Premium!")

    # Leaderboard
    st.markdown("### Leaderboard (Top 5)")
    board = db.get_leaderboard(5)
    for i, e in enumerate(board):
        st.write(f"**#{i+1}** {e['name']} — {e['total_score']} pts")

    # Badges
    my_badges = db.get_user_badges(st.session_state.user_id)
    if my_badges:
        st.markdown("### My Badges")
        st.write(", ".join([BADGES.get(b, b) for b in my_badges]))

    # CSV Upload + AI Analysis
    st.markdown("### Upload CSV for AI Analysis")
    csv_file = st.file_uploader("Choose CSV file", type="csv")
    query = None
    resp = ""
    if csv_file:
        df = pd.read_csv(csv_file)
        st.write("**Preview**")
        st.dataframe(df.head())
        st.write("**Stats**")
        st.dataframe(df.describe())

        numeric_cols = df.select_dtypes(include='number').columns
        if len(numeric_cols) > 0:
            col = st.selectbox("Select column for chart", numeric_cols)
            fig, ax = plt.subplots()
            df[col].hist(ax=ax, bins=20)
            ax.set_title(f"Distribution of {col}")
            st.pyplot(fig)

        csv_text = df.to_csv(index=False)
        query = st.text_input("Ask AI about this data:")
        if query:
            with st.spinner("Analyzing..."):
                prompt = f"CSV Data:\n{csv_text}\n\nQuestion: {query}\nProvide insights."
                resp = ai.generate_response(prompt, "You are a data analyst.")
            st.write("**AI Insights**")
            st.write(resp)

        if st.button("Export CSV Report to PDF"):
            pdf_buffer = generate_csv_pdf(df, query, resp if resp else "")
            # pdf_buffer is BytesIO with pointer at 0
            st.download_button("Download PDF", data=pdf_buffer.getvalue(), file_name="csv_analysis.pdf", mime="application/pdf")

    # Subject + Mode
    subject = st.sidebar.selectbox("Subject", list(SUBJECT_PROMPTS.keys()))
    mode = st.sidebar.radio("Mode", ["Chat", "Quiz"], horizontal=True)
    if mode == "Quiz":
        show_quiz_mode(subject)
    else:
        show_chat_mode(subject)

# =============================================
# 10. PDF GENERATORS
# =============================================
def generate_csv_pdf(df, question, insight):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("LearnFlow AI - CSV Analysis Report", styles['Title']))
    elements.append(Spacer(1, 0.2*inch))
    elements.append(Paragraph(f"User: {st.session_state.get('user_name','-')}", styles['Normal']))
    elements.append(Paragraph(f"Date: {time.strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 0.3*inch))

    if question:
        elements.append(Paragraph(f"<b>Question:</b> {question}", styles['Normal']))
    if insight:
        elements.append(Paragraph("<b>AI Insights:</b>", styles['Normal']))
        for line in insight.split('\n'):
            elements.append(Paragraph(line, styles['Normal']))
        elements.append(Spacer(1, 0.3*inch))

    # Limit the table size in the PDF to avoid huge documents
    max_rows = 100
    trimmed = df.head(max_rows)
    data = [trimmed.columns.tolist()] + trimmed.values.tolist()
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#00d4b1')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.25, colors.black),
        ('FONTSIZE', (0,0), (-1,-1), 8),
    ]))
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer

def generate_quiz_pdf(result, subject):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("LearnFlow AI - Quiz Report", styles['Title']))
    elements.append(Paragraph(f"Subject: {subject}", styles['Normal']))
    elements.append(Paragraph(f"Score: {result['correct']}/{result['total']} ({result['percentage']}%)", styles['Normal']))
    elements.append(Paragraph(f"Date: {time.strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 0.3*inch))

    for r in result["results"]:
        elements.append(Paragraph(f"<b>Q:</b> {r['question']}", styles['Normal']))
        elements.append(Paragraph(f"Your: {r['user_answer']} | Correct: {r['correct_answer']}", styles['Normal']))
        if not r["is_correct"]:
            elements.append(Paragraph(f"Feedback: {r.get('feedback','')}", styles['Italic']))
        elements.append(Spacer(1, 0.2*inch))

    doc.build(elements)
    buffer.seek(0)
    return buffer

# =============================================
# 11. QUIZ & CHAT
# =============================================
def show_chat_mode(subject):
    st.header(subject)
    prompt = st.chat_input("Ask me anything...")
    if prompt:
        with st.chat_message("user"): st.write(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                resp = ai.generate_response(f"{SUBJECT_PROMPTS[subject]}\nStudent: {prompt}", SUBJECT_PROMPTS[subject])
            st.write(resp)

def show_quiz_mode(subject):
    st.header(f"Quiz – {subject}")
    if st.button("Start 5-Question Quiz"):
        qs = ai.generate_mcq_questions(subject, 5)
        st.session_state.quiz = {"questions": qs, "answers": {}, "start": time.time()}
        st.experimental_rerun()

    if "quiz" in st.session_state:
        q = st.session_state.quiz
        for i, ques in enumerate(q["questions"]):
            with st.expander(f"Q{i+1}: {ques['question']}"):
                ans = st.radio("Choose", ques["options"], key=f"q{i}")
                q["answers"][i] = ans

        if st.button("Submit Quiz"):
            res = ai.grade_mcq(q["questions"], q["answers"])
            db.record_quiz_score(st.session_state.user_id, subject, res["correct"], res["total"])
            db.unlock_badge(st.session_state.user_id, "first_quiz")
            if res["percentage"] == 100:
                db.unlock_badge(st.session_state.user_id, "perfect_score")

            st.success(f"Score: {res['correct']}/{res['total']} ({res['percentage']}%)")
            for r in res["results"]:
                st.write(f"**Q:** {r['question']}")
                st.write(f"Your: {r['user_answer']} | Correct: {r['correct_answer']}")
                if not r["is_correct"]: st.info(r["feedback"])

            if st.button("Export Quiz Report to PDF"):
                pdf_buffer = generate_quiz_pdf(res, subject)
                st.download_button("Download PDF", data=pdf_buffer.getvalue(), file_name=f"quiz_{subject}.pdf", mime="application/pdf")

            del st.session_state.quiz
            st.experimental_rerun()

# =============================================
# 12. ROUTER
# =============================================
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
    st.experimental_rerun()
