# app.py — FINAL 2025 | FULLY WORKING | LOGIN/REGISTER FIXED | SPECIFIC TOPICS ADDED | GAMIFICATION/SHOP RESTORED | AI FIXED | ADMIN CONTROLS + PAYMENTS
import streamlit as st
import bcrypt
import pandas as pd
import json
from io import BytesIO
import PyPDF2
from datetime import datetime, timedelta

# ======================== SIMPLE IN-MEMORY DB ========================
if "db" not in st.session_state:
    st.session_state.db = {"users": {}, "scores": [], "payments": []}

db = st.session_state.db

# Create Emperor Admin (once)
if "kingmumo15@gmail.com" not in db["users"]:
    db["users"]["kingmumo15@gmail.com"] = {
        "user_id": 1,
        "email": "kingmumo15@gmail.com",
        "password_hash": bcrypt.hashpw("@Unruly10".encode(), bcrypt.gensalt()),
        "username": "EmperorUnruly",
        "level": 999,
        "xp_coins": 9999999,
        "total_xp": 9999999,
        "is_premium": True,
        "premium_expiry": None,
        "is_banned": False,
        "discount_20": True
    }

# ======================== AI ENGINE (NO EXTERNAL FILE) ========================
class AIEngine:
    def __init__(self):
        self.key = st.secrets.get("OPENAI_API_KEY")
        if not self.key:
            st.error("OPENAI_API_KEY is not set or invalid. Check Streamlit Secrets!")
            self.client = None
            return
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.key)
            self.model = "gpt-4o-mini"
        except Exception as e:
            st.error(f"OpenAI Init Error: {e}")
            self.client = None

    def call(self, system, user, temp=0.7):
        if not self.client:
            return "AI offline"
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=temp
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            return f"AI error: {e} (Check if key is valid and has credits)"

    def generate_exam_questions(self, subject, exam, count, topic):
        prompt = f"""
        Generate exactly {count} MCQs for {exam} {subject} on '{topic}'.
        Kenyan curriculum. 4 options A B C D. One correct.
        Output ONLY valid JSON array:
        [
          {{"question": "Example?", "options": ["A: Opt1", "B: Opt2", "C: Opt3", "D: Opt4"], "answer": "A: Opt1"}}
        ]
        No extra text.
        """
        try:
            from openai import OpenAI
            client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
            resp = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.1)
            text = resp.choices[0].message.content.strip()
            text = text.replace("```json","").replace("```","").strip()
            return json.loads(text)
        except Exception as e:
            st.error(f"Question Gen Error: {e}")
            return [{"question": f"{subject} Q{i+1}", "options": ["A: Correct", "B: Wrong", "C: Maybe", "D: None"], "answer": "A: Correct"} for i in range(count)]

ai_engine = AIEngine()

# ======================== SESSION STATE ========================
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user" not in st.session_state: st.session_state.user = None
if "page" not in st.session_state: st.session_state.page = "home"
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "questions" not in st.session_state: st.session_state.questions = []
if "user_answers" not in st.session_state: st.session_state.user_answers = {}
if "pdf_text" not in st.session_state: st.session_state.pdf_text = ""

# ======================== SUBJECTS & TOPICS (SPECIFIC NOW) ========================
EXAMS = ["Grade 6 KPSEA", "Grade 9 KJSEA", "KCSE 2025"]
SUBJECTS = {
    "Grade 6 KPSEA": ["Mathematics", "English", "Kiswahili", "Integrated Science", "Creative Arts & Social Studies"],
    "Grade 9 KJSEA": ["Mathematics", "English", "Kiswahili", "Integrated Science", "Agriculture & Nutrition", "Pre-Technical Studies"],
    "KCSE 2025": ["Mathematics", "English", "Kiswahili", "Biology", "Physics", "Chemistry", "History & Government",
                  "Geography", "CRE", "Computer Studies", "Business Studies", "Agriculture", "Home Science", "Python Programming"]
}

TOPICS = {
    # KPSEA Topics
    "Mathematics": ["Numbers", "Measurement", "Geometry", "Data Handling", "Algebra Basics"],
    "English": ["Comprehension", "Grammar", "Vocabulary", "Composition", "Oral Skills"],
    "Kiswahili": ["Ufahamu", "Sarufi", "Msamiati", "Insha", "Uwezo wa Kusikiliza"],
    "Integrated Science": ["Plants & Animals", "Human Body", "Environment", "Energy", "Matter & Materials"],
    "Creative Arts & Social Studies": ["Art & Craft", "Music", "Movement Activities", "Social Studies", "Religious Education"],

    # KJSEA Topics
    "Agriculture & Nutrition": ["Crop Production", "Animal Husbandry", "Soil Science", "Nutrition Basics", "Food Preservation"],
    "Pre-Technical Studies": ["Basic Engineering", "Technical Drawing", "Materials & Tools", "Safety Practices", "Simple Machines"],

    # KCSE Topics (including Python)
    "Biology": ["Cell Biology", "Genetics", "Ecology", "Human Physiology", "Evolution"],
    "Physics": ["Mechanics", "Electricity", "Waves", "Optics", "Thermal Physics"],
    "Chemistry": ["Atomic Structure", "Chemical Bonding", "Organic Chemistry", "Rates of Reaction", "Electrochemistry"],
    "History & Government": ["World History", "Kenyan History", "Government Systems", "African History", "International Relations"],
    "Geography": ["Physical Geography", "Human Geography", "Map Reading", "Climatology", "Environmental Management"],
    "CRE": ["Old Testament", "New Testament", "Christian Ethics", "African Religious Heritage", "Contemporary Issues"],
    "Computer Studies": ["Hardware", "Software", "Networking", "Programming Basics", "Data Representation"],
    "Business Studies": ["Entrepreneurship", "Accounting", "Marketing", "Business Law", "Economics"],
    "Home Science": ["Nutrition", "Textiles", "Home Management", "Consumer Education", "Child Care"],
    "Python Programming": ["Variables & Data Types", "Control Structures", "Functions & Modules", "Data Structures (Lists, Dicts)", "OOP", "File Handling", "Libraries (Pandas, Numpy)"]
}

# ======================== ANIMATED LANDING PAGE ========================
def landing_page():
    st.markdown("""
    <style>
    .hero{background:linear-gradient(135deg,#000000,#006400,#FF0000,#FFD700);
          padding:120px 20px;text-align:center;border-radius:30px;
          margin:-100px auto 50px;box-shadow:0 0 40px gold;
          animation:glow 3s infinite alternate}
    @keyframes glow{from{box-shadow:0 0 30px gold}to{box-shadow:0 0 60px #00ff9d}}
    .title{font-size:6rem;color:gold;font-weight:bold}
    .subtitle{font-size:2.5rem;color:white}
    </style>

    <div class="hero">
        <h1 class="title">KENYAN EDTECH</h1>
        <p class="subtitle">Kenya's #1 AI Exam & Tutor App</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        if st.button("LOGIN", use_container_width=True, type="primary"):
            st.session_state.page = "login"
            st.rerun()
        if st.button("REGISTER FREE", use_container_width=True):
            st.session_state.page = "register"
            st.rerun()

# ======================== LOGIN / REGISTER ========================
if not st.session_state.logged_in:
    if st.session_state.page == "login":
        st.title("Login")
        with st.form("login_form"):
            email = st.text_input("Email")
            pwd = st.text_input("Password", type="password")
            if st.form_submit_button("Login"):
                user = db["users"].get(email.lower())
                if user and bcrypt.checkpw(pwd.encode(), user["password_hash"]):
                    st.session_state.logged_in = True
                    st.session_state.user = user
                    st.success("Welcome back!")
                    st.rerun()
                else:
                    st.error("Wrong email or password")

    elif st.session_state.page == "register":
        st.title("Register Free Account")
        with st.form("register_form"):
            email = st.text_input("Email")
            pwd = st.text_input("Password", type="password")
            if st.form_submit_button("Create Account"):
                if email and pwd and email not in db["users"]:
                    db["users"][email] = {
                        "user_id": len(db["users"])+1,
                        "email": email,
                        "password_hash": bcrypt.hashpw(pwd.encode(), bcrypt.gensalt()),
                        "username": email.split("@")[0],
                        "level": 1, "xp_coins": 100, "total_xp": 100,
                        "is_premium": False, "premium_expiry": None, "is_banned": False
                    }
                    st.success("Account created! Now login.")
                    st.session_state.page = "login"
                    st.rerun()
                else:
                    st.error("Email already exists or empty")

    else:
        landing_page()

# ======================== MAIN DASHBOARD ========================
else:
    user = st.session_state.user
    is_admin = user["email"] == "kingmumo15@gmail.com"

    # Auto-downgrade premium if expired
    if user.get("premium_expiry") and datetime.fromisoformat(user["premium_expiry"]) < datetime.now():
        user["is_premium"] = False
        user["premium_expiry"] = None

    # Calculate level from XP (gamification)
    xp = user.get("total_xp", 0)
    level = 1
    xp_needed = 100
    while xp >= xp_needed:
        xp -= xp_needed
        level += 1
        xp_needed = int(xp_needed * 1.2)
    user["level"] = level

    with st.sidebar:
        st.image("https://flagcdn.com/w320/ke.png", width=100)
        st.success(f"**{user.get('username','Student')}**")
        st.metric("Level", user["level"])
        st.metric("XP Coins", f"{user.get('xp_coins',0):,}")
        st.metric("Total XP", f"{user.get('total_xp',0):,}")
        if user.get("is_premium"): st.success("Premium Active!")
        if st.button("Logout"):
            st.session_state.clear()
            st.rerun()

    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["AI Tutor", "Exam Prep", "PDF Q&A", "Progress", "XP Shop", "Premium", "Admin"])

    with tab1:
        st.header("AI Tutor")
        subject = st.selectbox("Subject", SUBJECTS["KCSE 2025"])
        for msg in st.session_state.chat_history:
            st.chat_message(msg["role"]).write(msg["content"])
        if prompt := st.chat_input("Ask anything..."):
            st.session_state.chat_history.append({"role":"user","content":prompt})
            with st.chat_message("assistant"):
                reply = ai_engine.call("You are an expert Kenyan curriculum tutor.", prompt + f"\nSubject: {subject}")
                st.write(reply)
            st.session_state.chat_history.append({"role":"assistant","content":reply})
            # Award XP for asking question
            user["total_xp"] = user.get("total_xp",0) + 10
            user["xp_coins"] = user.get("xp_coins",0) + 10

    with tab2:
        st.header("Exam Practice")
        exam = st.selectbox("Exam", EXAMS)
        subject = st.selectbox("Subject", SUBJECTS[exam])
        topic = st.selectbox("Topic", TOPICS.get(subject, ["General"]))
        count = st.slider("Questions", 10, 50, 25)
        if st.button("Generate Exam", type="primary"):
            with st.spinner("Creating high-quality questions..."):
                st.session_state.questions = ai_engine.generate_exam_questions(subject, exam, count, topic)
                st.session_state.user_answers = {}
                st.success("Exam ready!")

        if st.session_state.questions:
            for i, q in enumerate(st.session_state.questions):
                st.write(f"**Q{i+1}.** {q['question']}")
                ans = st.radio("Choose", q["options"], key=f"ans{i}")
                st.session_state.user_answers[i] = ans.split(":")[0].strip()

            if st.button("Submit Exam"):
                correct = sum(st.session_state.user_answers.get(i,"") == q["answer"].split(":")[0].strip() for i,q in enumerate(st.session_state.questions))
                score = round(correct / len(st.session_state.questions) * 100, 1)
                st.success(f"Score: {score}% — {correct}/{len(st.session_state.questions)}")
                xp_earned = int(score * 10)
                user["total_xp"] = user.get("total_xp",0) + xp_earned
                user["xp_coins"] = user.get("xp_coins",0) + xp_earned
                st.balloons()
                st.session_state.questions = []

    with tab3:
        st.header("PDF Q&A")
        uploaded = st.file_uploader("Upload your notes", type="pdf")
        if uploaded:
            text = ""
            reader = PyPDF2.PdfReader(BytesIO(uploaded.getvalue()))
            for page in reader.pages:
                text += page.extract_text() or ""
            st.session_state.pdf_text = text[:15000]
            st.success("PDF loaded! Ask questions below")

        if st.session_state.pdf_text and (q := st.chat_input("Ask about your PDF")):
            reply = ai_engine.call("Answer using ONLY this text:", q + "\n\nText:\n" + st.session_state.pdf_text)
            st.write(reply)
            # Award XP for PDF question
            user["total_xp"] = user.get("total_xp",0) + 15
            user["xp_coins"] = user.get("xp_coins",0) + 15

    with tab4:
        st.header("Your Progress")
        st.metric("Total XP", f"{user.get('total_xp',0):,}")
        st.metric("Level", user["level"])
        st.metric("XP Coins", f"{user.get('xp_coins',0):,}")

    with tab5:
        st.header("XP Shop")
        coins = user.get("xp_coins", 0)
        items = [
            ("20% Discount Cheque", 5000000, "discount_20"),
            ("Extra Daily Questions (+10)", 100, "extra_questions"),
            ("Custom Badge", 500000, "custom_badge"),
            ("Extra AI Uses (+50)", 200000, "extra_ai"),
            ("Profile Theme", 300000, "profile_theme")
        ]
        for name, price, field in items:
            if st.button(f"Buy {name} — {price:,} XP Coins"):
                if coins >= price:
                    user["xp_coins"] -= price
                    user[field] = user.get(field, 0) + 1
                    st.success(f"Purchased {name}!")
                    st.balloons()
                else:
                    st.error("Not enough XP Coins")

    with tab6:
        st.header("Premium Subscription")
        if is_admin:
            st.success("EMPEROR ACCOUNT — UNLIMITED PREMIUM")
        elif user.get("is_premium"):
            st.success(f"Premium Active! Expires: {user['premium_expiry']}")
        else:
            st.info("Send KSh 600 to 0701617120 for 1 Month Premium")
            mpesa_code = st.text_input("Enter M-Pesa Code after payment")
            if st.button("Submit Payment"):
                db["payments"].append({
                    "user_id": user["user_id"],
                    "mpesa_code": mpesa_code,
                    "timestamp": datetime.now().isoformat(),
                    "status": "pending"
                })
                st.success("Payment submitted! Waiting for admin approval.")

    with tab7:
        if is_admin:
            st.header("Admin Control Panel")
            users = list(db["users"].values())
            for u in users:
                with st.expander(f"User: {u['email']} (ID: {u['user_id']})"):
                    if st.button("Ban", key=f"ban_{u['user_id']}"):
                        u["is_banned"] = True
                        st.success("User banned")
                    if st.button("Unban", key=f"unban_{u['user_id']}"):
                        u["is_banned"] = False
                        st.success("User unbanned")
                    if st.button("Upgrade to Premium (1 Month)", key=f"up_{u['user_id']}"):
                        u["is_premium"] = True
                        u["premium_expiry"] = (datetime.now() + timedelta(days=30)).isoformat()
                        st.success("Upgraded to Premium")
                    if st.button("Manual Downgrade to Basic", key=f"down_{u['user_id']}"):
                        u["is_premium"] = False
                        u["premium_expiry"] = None
                        st.success("Downgraded to Basic")

            st.subheader("Pending Payments")
            for p in db["payments"]:
                with st.expander(f"Payment from User ID {p['user_id']} - Code: {p['mpesa_code']}"):
                    if st.button("Approve Payment", key=f"approve_{p['timestamp']}"):
                        user_id = p["user_id"]
                        for usr in users:
                            if usr["user_id"] == user_id:
                                usr["is_premium"] = True
                                usr["premium_expiry"] = (datetime.now() + timedelta(days=30)).isoformat()
                                p["status"] = "approved"
                                st.success("Payment approved and user upgraded!")
                                break
        else:
            st.write("Access denied")