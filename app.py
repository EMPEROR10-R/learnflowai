# app.py — FIXED 2025: Users Start at 0 XP/Level/Coins (Except Admin) + More Shop Items + AI Tutor/Exam Gen Working + Unique Difficult Questions + All Features Intact
import streamlit as st
import bcrypt
import pandas as pd
import qrcode
import base64
from io import BytesIO
import matplotlib.pyplot as plt
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES
from utils import Translator_Utils, cached_pdf_extract

st.set_page_config(page_title="Kenyan EdTech", layout="wide", initial_sidebar_state="expanded")

# ============= INIT =============
db = Database()
# THIS NOW WORKS PERFECTLY — auto-downgrades expired premium users
db.auto_downgrade() 
# Initialize AI Engine (it will read the key from st.secrets['OPENAI_API_KEY'] internally)
ai_engine = AIEngine()

XP_RULES = {"question_asked": 10, "pdf_question": 15, "2fa_enabled": 20}

if "page" not in st.session_state:
    st.session_state.page = "landing"
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = None
if "user" not in st.session_state:
    st.session_state.user = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "pdf_text" not in st.session_state:
    st.session_state.pdf_text = ""
if "current_subject" not in st.session_state:
    st.session_state.current_subject = "Mathematics"
if "show_qr" not in st.session_state:
    st.session_state.show_qr = False
if "secret_key" not in st.session_state:
    st.session_state.secret_key = None
if "qr_code" not in st.session_state:
    st.session_state.qr_code = None
if "show_2fa" not in st.session_state:
    st.session_state.show_2fa = False
if "temp_user" not in st.session_state:
    st.session_state.temp_user = None
if "questions" not in st.session_state:
    st.session_state.questions = []
if "user_answers" not in st.session_state:
    st.session_state.user_answers = {}

translator = Translator_Utils()

# ============= KENYAN HERO (100% SAFE) =============
st.markdown("""
<style>
    .hero {background: linear-gradient(135deg, #000000, #006400, #FFD700, #B30000);
           padding: 100px 20px; border-radius: 25px; text-align: center;
           margin: -90px auto 50px; box-shadow: 0 20px 50px rgba(0,0,0,0.7);}
    .title {font-size: 5.5rem; color: #FFD700; font-weight: bold; text-shadow: 5px 5px 15px #000;}
    .subtitle {font-size: 2.4rem; color: #00ff9d;}
    .big-btn {background: linear-gradient(45deg, #00ff9d, #00cc7a); color: white;
              padding: 25px; font-size: 30px; font-weight: bold; border-radius: 20px;
              border: none; width: 100%; margin: 20px 0; box-shadow: 0 15px 40px rgba(0,255,157,0.6);}
    .big-btn:hover {transform: translateY(-12px); box-shadow: 0 30px 60px rgba(0,255,157,0.8);}
    .shop-item {animation: fadeIn 0.5s ease-in-out;}
    @keyframes fadeIn {0% {opacity: 0;} 100% {opacity: 1;}}
</style>
<div class="hero">
    <h1 class="title">Kenyan EdTech</h1>
    <p class="subtitle">Kenya's Most Powerful AI Tutor</p>
</div>
""", unsafe_allow_html=True)

# ============= HELPERS =============
def get_user():
    if st.session_state.user_id:
        # Re-fetch the user to update session state with latest XP, premium status, etc.
        st.session_state.user = db.get_user(st.session_state.user_id)
    return st.session_state.user

def award_xp(points, reason):
    if st.session_state.user_id:
        db.add_xp(st.session_state.user_id, points)
        get_user()
        st.toast(f"+{points} XP & Coins — {reason}")
        st.balloons()  # Animation on XP award

def calculate_level_progress(total_xp):
    if total_xp == 0:
        return 0, 0.0, 0, 100  # Start at level 0
    level = 0
    xp_needed = 100
    current_xp = total_xp
    while current_xp >= xp_needed:
        current_xp -= xp_needed
        level += 1
        xp_needed = int(xp_needed * 1.5)  # Exponential increase
    progress = current_xp / xp_needed
    return level, progress, current_xp, xp_needed

def calculate_item_price(base_price, buy_count):
    # Exponential price increase based on how many times it has been bought
    return int(base_price * (2 ** buy_count))

# ============= PAGE RENDERING =============
if st.session_state.page == "landing" and not st.session_state.logged_in:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("LOGIN", use_container_width=True, key="landing_login", type="primary"):
            st.session_state.page = "login"
            st.rerun()
        if st.button("REGISTER", use_container_width=True, key="landing_register"):
            st.session_state.page = "register"
            st.rerun()

elif st.session_state.page == "login":
    st.markdown("### Login to Your Account")
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("Login"):
                user = db.get_user_by_email(email)
                if user and bcrypt.checkpw(password.encode(), user["password_hash"]):
                    st.session_state.temp_user = user
                    if db.is_2fa_enabled(user["user_id"]):
                        st.session_state.show_2fa = True
                        st.session_state.page = "2fa"
                    else:
                        st.session_state.logged_in = True
                        st.session_state.user_id = user["user_id"]
                        st.session_state.page = "main"
                    st.rerun()
                else:
                    st.error("Invalid credentials")
        with col2:
            if st.form_submit_button("Back"):
                st.session_state.page = "landing"
                st.rerun()

elif st.session_state.page == "register":
    st.markdown("### Create Account")
    with st.form("register_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm Password", type="password")
        if password != confirm and password:
            st.error("Passwords do not match")
        col1, col2 = st.columns(2)
        with col1:
            if st.form_submit_button("Register"):
                if db.create_user(email, password):
                    st.success("Account created! Please login.")
                    st.session_state.page = "login"
                    st.rerun()
                else:
                    st.error("Email already exists")
        with col2:
            if st.form_submit_button("Back"):
                st.session_state.page = "landing"
                st.rerun()

elif st.session_state.page == "2fa":
    st.header("Two-Factor Authentication")
    code = st.text_input("Enter 6-digit code", key="2fa_input")
    if st.button("Verify", key="verify_2fa"):
        if db.verify_2fa_code(st.session_state.temp_user["user_id"], code):
            st.session_state.logged_in = True
            st.session_state.user_id = st.session_state.temp_user["user_id"]
            del st.session_state.temp_user
            st.session_state.show_2fa = False
            st.session_state.page = "main"
            st.rerun()
        else:
            st.error("Invalid code")

elif st.session_state.logged_in and st.session_state.page == "main":
    with st.sidebar:
        st.title("Kenyan EdTech")
        u = get_user()
        
        # Check if user data exists (should always if logged in, but for safety)
        if not u:
            st.error("User data not found. Logging out...")
            st.session_state.logged_in = False
            st.session_state.page = "landing"
            st.rerun()
        
        st.write(f"**{u.get('username','Student')}**")
        level, progress, current_xp, xp_needed = calculate_level_progress(u.get('total_xp', 0))
        st.metric("Level", level)
        st.progress(progress)
        st.caption(f"{current_xp} / {xp_needed} XP to Level {level + 1}")
        st.metric("Total XP", f"{u.get('total_xp',0):,}")
        st.metric("XP Coins", f"{u.get('xp_coins',0):,}")
        st.metric("Streak", f"{u.get('streak',0)} days")
        
        # Premium status badge
        if u.get('is_premium', 0):
            st.success("✅ Premium Active!")
        else:
            st.warning("👤 Basic User")

        if u.get('discount_20'): st.info("🎉 20% Discount Cheque Active!")

        if st.button("Logout", use_container_width=True, type="secondary"):
            st.session_state.logged_in = False
            st.session_state.user_id = None
            st.session_state.user = None
            st.session_state.page = "landing"
            st.rerun()

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "Chat Tutor", "Exam Prep", "PDF Q&A", "Progress", "Essay Grader", "XP Shop", "Premium", "Settings"
    ])

    with tab1:
        st.header("AI Tutor")
        subject = st.selectbox("Subject", list(SUBJECT_PROMPTS.keys()), key="subject_select")
        st.session_state.current_subject = subject
        
        # Display chat history
        for msg in st.session_state.chat_history:
            st.chat_message(msg["role"]).write(msg["content"])
            
        if prompt := st.chat_input("Ask anything..."):
            # Add user message to history immediately
            st.session_state.chat_history.append({"role": "user", "content": prompt})
            
            with st.spinner("AI Tutor is thinking..."):
                # Get the system prompt
                system_prompt = get_enhanced_prompt(subject, prompt)
                # Generate the response using OpenAI
                resp = ai_engine.generate_response(prompt, system_prompt)
            
            # Add assistant response to history
            st.session_state.chat_history.append({"role": "assistant", "content": resp})
            award_xp(XP_RULES["question_asked"], "Question asked")
            st.rerun()  # Refresh chat

    with tab2:
        st.header("Exam Preparation")
        exam = st.selectbox("Exam", list(EXAM_TYPES.keys()))
        subject = st.selectbox("Subject", EXAM_TYPES[exam]["subjects"])
        topics = EXAM_TYPES[exam]["topics"].get(subject, ["General"])
        topic = st.selectbox("Topic", topics)
        num = st.slider("Questions", 1, 50, 10)
        
        if st.button("Generate Exam", key="generate_exam_btn"):
            with st.spinner(f"Generating {num} questions for {subject}... Please wait."):
                # Generate questions using OpenAI
                questions = ai_engine.generate_exam_questions(subject, exam, num, topic)
                
                # Check if generation was successful and store
                if questions and isinstance(questions, list):
                    st.session_state.questions = questions
                    st.session_state.user_answers = {}
                    st.success("Exam generated!")
                    st.balloons()  # Animation on success
                else:
                    st.error("Failed to generate exam questions. Please check AI Engine logs.")
        
        if st.session_state.questions:
            st.subheader(f"Current Exam: {subject} - {topic} ({len(st.session_state.questions)} Qs)")
            
            # Display questions and capture answers
            for i, q in enumerate(st.session_state.questions):
                st.markdown(f"**Q{i+1}:** {q.get('question', 'N/A')}")
                
                # Check for options validity
                options = q.get("options", [])
                if options and isinstance(options, list):
                    # Use the correct key for unique radio buttons
                    ans = st.radio("Choose answer", options, key=f"q_{i}", index=None)
                    st.session_state.user_answers[i] = ans
                else:
                    st.error(f"Error: Question {i+1} options are invalid.")
            
            # Submission logic
            if st.button("Submit Exam", key="submit_exam_btn"):
                with st.spinner("Grading your exam..."):
                    result = ai_engine.grade_mcq(st.session_state.questions, st.session_state.user_answers)
                
                st.subheader(f"Results: {result['score']} / {result['total']}")
                st.success(f"Final Percentage: {result['percentage']}%")
                
                # Record score and award XP
                db.add_score(st.session_state.user_id, f'exam_{subject}', result['percentage'])
                award_xp(int(result["percentage"]), "Exam Completion")
                st.snow()  # Animation on submit
                
                # Display detailed feedback
                with st.expander("Detailed Feedback", expanded=False):
                    for fb in result['feedback']:
                        icon = "✅" if fb['is_correct'] else "❌"
                        st.markdown(f"**{icon} {fb['question']}**")
                        st.caption(f"Your Answer: **{fb['user_answer']}**")
                        st.caption(f"Correct Answer: **{fb['correct_answer']}**")
                        st.markdown("---")


    with tab3:
        st.header("PDF Q&A")
        uploaded = st.file_uploader("Upload PDF", type="pdf")
        
        if uploaded:
            # Use cached function to extract text
            st.session_state.pdf_text = cached_pdf_extract(uploaded.getvalue(), uploaded.name)
            st.success(f"PDF '{uploaded.name}' loaded! Text size: {len(st.session_state.pdf_text):,} characters.")
            st.markdown("---")
            
            # Chat input for PDF
            if q := st.chat_input("Ask a question about the uploaded PDF..."):
                with st.spinner("Searching and generating answer from PDF..."):
                    # Use the extracted text as context, limiting to first 12000 chars for API efficiency
                    context = f"Document Text:\n{st.session_state.pdf_text[:12000]}"
                    
                    # Generate response using OpenAI
                    resp = ai_engine.generate_response(
                        user_query=q, 
                        system_prompt=get_enhanced_prompt("General", q, context=context)
                    )
                    
                    st.chat_message("user").write(q)
                    st.chat_message("assistant").write(resp)
                    award_xp(XP_RULES["pdf_question"], "PDF Question")

    with tab4:
        st.header("Your Progress & Leaderboards")
        u = get_user()
        st.metric("Total XP", u.get("total_xp", 0))
        
        # Leaderboard 1: Global Level Leaderboard
        st.subheader("Global Level Leaderboard")
        lb = db.get_xp_leaderboard()
        if lb:
            df = pd.DataFrame([
                {"Rank": i+1, "Email": r["email"], "XP": r["total_xp"], "Level": calculate_level_progress(r["total_xp"])[0]} 
                for i, r in enumerate(lb)
            ])
            st.dataframe(df, hide_index=True, use_container_width=True)
            # Graph
            fig, ax = plt.subplots(figsize=(10, 5))
            ax.bar(df["Email"], df["Level"], color='#00ff9d')
            ax.set_ylabel("Level")
            ax.set_title("Global Levels Graph")
            ax.tick_params(axis='x', rotation=45)
            st.pyplot(fig)
        else:
            st.info("No users yet to form a leaderboard.")

        # Leaderboard 2: Subject Exam Leaderboards
        st.subheader("Subject Exam Leaderboards")
        selected_subject = st.selectbox("Select Subject for Leaderboard", list(SUBJECT_PROMPTS.keys()), key="lb_subject_select")
        subject_lb = db.get_leaderboard(f'exam_{selected_subject}')
        if subject_lb:
            df_subject = pd.DataFrame([
                {"Rank": i+1, "Email": r["email"], "Avg Score": f"{r['score']:.1f}%"} 
                for i, r in enumerate(subject_lb)
            ])
            st.dataframe(df_subject, hide_index=True, use_container_width=True)
            # Graph
            fig2, ax2 = plt.subplots(figsize=(10, 5))
            scores = [float(r['score']) for r in subject_lb]
            emails = [r['email'] for r in subject_lb]
            ax2.bar(emails, scores, color='#FFD700')
            ax2.set_ylabel("Average Score (%)")
            ax2.set_title(f"{selected_subject} Average Scores Graph")
            ax2.tick_params(axis='x', rotation=45)
            st.pyplot(fig2)
        else:
            st.info(f"No exam scores recorded for {selected_subject} yet.")

        # Leaderboard 3: Essay Grader Leaderboard
        st.subheader("Essay Grader Leaderboard")
        essay_lb = db.get_leaderboard('essay')
        if essay_lb:
            df_essay = pd.DataFrame([
                {"Rank": i+1, "Email": r["email"], "Avg Score": f"{r['score']:.1f}/20"} 
                for i, r in enumerate(essay_lb)
            ])
            st.dataframe(df_essay, hide_index=True, use_container_width=True)
            # Graph
            fig3, ax3 = plt.subplots(figsize=(10, 5))
            scores = [float(r['score']) for r in essay_lb]
            emails = [r['email'] for r in essay_lb]
            ax3.bar(emails, scores, color='#B30000')
            ax3.set_ylabel("Average Score (Max 20)")
            ax3.set_title("Essay Scores Graph")
            ax3.tick_params(axis='x', rotation=45)
            st.pyplot(fig3)
        else:
            st.info("No essay scores recorded yet.")

    with tab5:
        st.header("Essay Grader")
        essay = st.text_area("Paste your essay here for grading", height=300)
        
        if st.button("Grade Essay", key="grade_essay_btn"):
            if not essay.strip():
                st.warning("Please paste an essay to be graded.")
            else:
                with st.spinner("AI Marker is grading..."):
                    # Grade essay using OpenAI
                    result = ai_engine.grade_essay(essay, "KCSE Standard Rubric")
                
                # Ensure the result structure is valid
                score = result.get('score', 0)
                max_score = result.get('max_score', 20)
                
                st.subheader(f"Final Score: {score} / {max_score}")
                st.info(f"Feedback: {result.get('feedback', 'No feedback provided.')}")
                st.warning(f"Suggestions: {result.get('suggestions', 'No suggestions provided.')}")
                
                db.add_score(st.session_state.user_id, 'essay', score)
                award_xp(score * 5, "Essay Graded") # Award 5 XP per point scored

    with tab6:
        st.header("XP Shop")
        st.markdown(f"**Your Current Balance:** <span style='font-size: 24px; color: #FFD700;'>{u.get('xp_coins', 0):,} XP Coins</span>", unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        # --- Item 1: Discount Cheque ---
        with col1:
            st.markdown('<div class="shop-item" style="border: 2px solid #00ff9d; padding: 15px; border-radius: 10px;">', unsafe_allow_html=True)
            discount_buy_count = u.get('discount_buy_count', 0)
            discount_price = calculate_item_price(5000000, discount_buy_count)
            st.subheader("20% Premium Discount")
            st.write(f"Price: **{discount_price:,} XP Coins**")
            if u.get('discount_20'):
                st.success("Already Active!")
            elif st.button("Buy Discount Cheque", key="buy_discount", use_container_width=True):
                if db.buy_discount_cheque(st.session_state.user_id, discount_price):
                    st.balloons()
                    st.success("Discount Activated!")
                    st.rerun()
                else:
                    st.error("Not enough XP Coins")
            st.markdown('</div>', unsafe_allow_html=True)
            
        # --- Item 2: Extra Daily Questions ---
        with col2:
            st.markdown('<div class="shop-item" style="border: 2px solid #00ff9d; padding: 15px; border-radius: 10px;">', unsafe_allow_html=True)
            extra_questions_count = u.get('extra_questions_buy_count', 0)
            extra_questions_price = calculate_item_price(100, max(0, extra_questions_count))
            st.subheader("Extra Daily Questions (+10)")
            st.write(f"Price: **{extra_questions_price:,} XP Coins**")
            if st.button("Buy Extra Questions", key="buy_extra_q", use_container_width=True):
                if db.buy_extra_questions(st.session_state.user_id, extra_questions_price):
                    st.success("Extra Questions Added!")
                    st.snow()
                    st.rerun()
                else:
                    st.error("Not enough XP Coins")
            st.markdown('</div>', unsafe_allow_html=True)
            
        # --- Item 3: Custom Badge ---
        with col3:
            st.markdown('<div class="shop-item" style="border: 2px solid #00ff9d; padding: 15px; border-radius: 10px;">', unsafe_allow_html=True)
            custom_badge_count = u.get('custom_badge_buy_count', 0)
            custom_badge_price = calculate_item_price(500000, max(0, custom_badge_count))
            st.subheader("Custom Badge")
            st.write(f"Price: **{custom_badge_price:,} XP Coins**")
            if st.button("Buy Custom Badge", key="buy_custom_badge", use_container_width=True):
                if db.buy_custom_badge(st.session_state.user_id, custom_badge_price):
                    st.success("Custom Badge Unlocked!")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("Not enough XP Coins")
            st.markdown('</div>', unsafe_allow_html=True)

        col4, col5, col6 = st.columns(3)
        
        # --- Item 4: Extra AI Uses ---
        with col4:
            st.markdown('<div class="shop-item" style="border: 2px solid #00ff9d; padding: 15px; border-radius: 10px;">', unsafe_allow_html=True)
            extra_ai_count = u.get('extra_ai_uses_buy_count', 0)
            extra_ai_price = calculate_item_price(200000, max(0, extra_ai_count))
            st.subheader("Extra AI Uses (+50 Queries)")
            st.write(f"Price: **{extra_ai_price:,} XP Coins**")
            if st.button("Buy Extra AI Uses", key="buy_extra_ai", use_container_width=True):
                if db.buy_extra_ai_uses(st.session_state.user_id, extra_ai_price):
                    st.success("Extra AI Uses Added!")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("Not enough XP Coins")
            st.markdown('</div>', unsafe_allow_html=True)
            
        # --- Item 5: Profile Theme ---
        with col5:
            st.markdown('<div class="shop-item" style="border: 2px solid #00ff9d; padding: 15px; border-radius: 10px;">', unsafe_allow_html=True)
            profile_theme_count = u.get('profile_theme_buy_count', 0)
            profile_theme_price = calculate_item_price(300000, max(0, profile_theme_count))
            st.subheader("Profile Theme Unlock")
            st.write(f"Price: **{profile_theme_price:,} XP Coins**")
            if st.button("Buy Profile Theme", key="buy_theme", use_container_width=True):
                if db.buy_profile_theme(st.session_state.user_id, profile_theme_price):
                    st.success("Profile Theme Unlocked!")
                    st.snow()
                    st.rerun()
                else:
                    st.error("Not enough XP Coins")
            st.markdown('</div>', unsafe_allow_html=True)
            
        # --- Item 6: Unlock Advanced Topics ---
        with col6:
            st.markdown('<div class="shop-item" style="border: 2px solid #00ff9d; padding: 15px; border-radius: 10px;">', unsafe_allow_html=True)
            advanced_topics_count = u.get('advanced_topics_buy_count', 0)
            advanced_topics_price = calculate_item_price(1000000, max(0, advanced_topics_count))
            st.subheader("Unlock Advanced Topics")
            st.write(f"Price: **{advanced_topics_price:,} XP Coins**")
            if st.button("Buy Advanced Topics", key="buy_advanced", use_container_width=True):
                if db.buy_advanced_topics(st.session_state.user_id, advanced_topics_price):
                    st.success("Advanced Topics Unlocked!")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("Not enough XP Coins")
            st.markdown('</div>', unsafe_allow_html=True)

        col7, col8 = st.columns(2)
        
        # --- Item 7: Custom Avatar ---
        with col7:
            st.markdown('<div class="shop-item" style="border: 2px solid #00ff9d; padding: 15px; border-radius: 10px;">', unsafe_allow_html=True)
            custom_avatar_count = u.get('custom_avatar_buy_count', 0)
            custom_avatar_price = calculate_item_price(400000, max(0, custom_avatar_count))
            st.subheader("Custom Avatar")
            st.write(f"Price: **{custom_avatar_price:,} XP Coins**")
            if st.button("Buy Custom Avatar", key="buy_avatar", use_container_width=True):
                if db.buy_custom_avatar(st.session_state.user_id, custom_avatar_price):
                    st.success("Custom Avatar Unlocked!")
                    st.snow()
                    st.rerun()
                else:
                    st.error("Not enough XP Coins")
            st.markdown('</div>', unsafe_allow_html=True)

        # --- Item 8: Priority Support ---
        with col8:
            st.markdown('<div class="shop-item" style="border: 2px solid #00ff9d; padding: 15px; border-radius: 10px;">', unsafe_allow_html=True)
            priority_support_count = u.get('priority_support_buy_count', 0)
            priority_support_price = calculate_item_price(1500000, max(0, priority_support_count))
            st.subheader("Priority Support")
            st.write(f"Price: **{priority_support_price:,} XP Coins**")
            if st.button("Buy Priority Support", key="buy_priority", use_container_width=True):
                if db.buy_priority_support(st.session_state.user_id, priority_support_price):
                    st.success("Priority Support Unlocked!")
                    st.balloons()
                    st.rerun()
                else:
                    st.error("Not enough XP Coins")
            st.markdown('</div>', unsafe_allow_html=True)

        # Inventory Tracking Table
        st.subheader("Your Inventory")
        purchases = db.get_user_purchases(st.session_state.user_id)
        if purchases:
            df_purchases = pd.DataFrame(purchases)
            df_purchases['timestamp'] = pd.to_datetime(df_purchases['timestamp']).dt.strftime('%Y-%m-%d %H:%M')
            st.dataframe(df_purchases[['item_name', 'quantity', 'price_paid', 'timestamp']], hide_index=True, use_container_width=True)
        else:
            st.info("No purchases yet.")

    with tab7:
        st.header("Go Premium")
        if u.get('username') == "EmperorUnruly":
            st.success("👑 Admin Account: Full-Time Premium Access")
        elif u.get('is_premium', 0) == 0:
            price = 480 if u.get("discount_20") else 600
            st.success(f"To activate Premium for one month, send **KSh {price}** to **0701617120** (M-Pesa).")
            with st.form("premium_payment"):
                phone = st.text_input("Your Phone Number (e.g., 07XXXXXXXX)", max_chars=10)
                code = st.text_input("M-Pesa Confirmation Code (e.g., QRT12ABC)", max_chars=10)
                if st.form_submit_button("Submit Payment Confirmation"):
                    if phone and code:
                        db.add_payment(st.session_state.user_id, phone, code)
                        st.success("Payment recorded! Awaiting admin approval to activate premium.")
                        st.rerun()
                    else:
                        st.error("Please enter both phone number and M-Pesa code.")
        else:
            # Display expiry date if premium
            expiry_date = u.get('premium_expiry', 'N/A')
            st.success(f"✅ You are Premium until **{expiry_date}**!")

    with tab8:
        st.header("Settings & Account Management")
        
        # Password Update Form
        st.subheader("Change Password")
        with st.form("update_password"):
            new_pass = st.text_input("New Password", type="password")
            confirm = st.text_input("Confirm New Password", type="password")
            if st.form_submit_button("Update Password"):
                if new_pass and new_pass == confirm:
                    db.update_password(st.session_state.user_id, new_pass)
                    st.success("Password updated successfully!")
                else:
                    st.error("Passwords do not match or field is empty.")
                    
        # 2FA Setup
        st.subheader("Two-Factor Authentication (2FA)")
        if not db.is_2fa_enabled(st.session_state.user_id):
            if st.button("Enable 2FA"):
                secret, qr = db.enable_2fa(st.session_state.user_id)
                buffered = BytesIO()
                qr.save(buffered)
                # Convert QR code to base64 string for display
                st.session_state.qr_code = base64.b64encode(buffered.getvalue()).decode()
                st.session_state.secret_key = secret
                st.session_state.show_qr = True
                st.rerun()
                
            if st.session_state.show_qr:
                st.warning("Scan this QR code with your authenticator app (e.g., Google Authenticator).")
                st.image(f"data:image/png;base64,{st.session_state.qr_code}", width=200)
                st.code(st.session_state.secret_key, language="text")
                
                code = st.text_input("Enter 6-digit code to confirm setup")
                if st.button("Confirm 2FA Setup"):
                    if db.verify_2fa_code(st.session_state.user_id, code):
                        db.finalize_2fa(st.session_state.user_id, st.session_state.secret_key)
                        st.success("2FA Enabled and saved! Remember your secret key.")
                        award_xp(XP_RULES["2fa_enabled"], "2FA Setup")
                        st.session_state.show_qr = False
                        st.rerun()
                    else:
                        st.error("Invalid code. Try again.")
        else:
            st.success("2FA is currently enabled on your account.")
            if st.button("Disable 2FA"):
                db.disable_2fa(st.session_state.user_id)
                st.warning("2FA has been disabled.")
                st.rerun()


        # Admin Control Center (Only visible to EmperorUnruly)
        if get_user().get("username") == "EmperorUnruly":
            st.subheader("👑 Admin Control Center")
            
            # --- User Management ---
            st.markdown("##### Manage Users & Premium Status")
            all_users = db.get_all_users()
            user_df = pd.DataFrame(all_users)
            user_df['is_premium_text'] = user_df['is_premium'].apply(lambda x: 'PREMIUM' if x else 'BASIC')
            st.dataframe(user_df[['user_id', 'email', 'is_premium_text', 'is_banned', 'premium_expiry']], hide_index=True, use_container_width=True)
            
            st.markdown("---")
            
            # Action buttons for each user
            for user in all_users:
                if user['username'] == "EmperorUnruly": continue # Skip admin self-management
                
                st.markdown(f"**{user['email']}** (Status: {'PREMIUM' if user['is_premium'] else 'BASIC'})")
                col1, col2, col3, col4, col5 = st.columns(5)
                
                # Ban/Unban
                with col1:
                    if user['is_banned'] == 0:
                        if st.button("🔴 Ban User", key=f"ban_{user['user_id']}", use_container_width=True):
                            db.ban_user(user['user_id'])
                            st.rerun()
                    else:
                        if st.button("🟢 Unban User", key=f"unban_{user['user_id']}", use_container_width=True):
                            db.unban_user(user['user_id'])
                            st.rerun()
                
                # Manual Upgrade/Downgrade (Handles the user's request)
                with col3:
                    if st.button("⬆️ Upgrade to Premium", key=f"upgrade_{user['user_id']}", use_container_width=True):
                        # This manually grants one month premium access
                        db.upgrade_to_premium(user['user_id'])
                        st.rerun()
                with col4:
                    if st.button("⬇️ Downgrade to Basic", key=f"downgrade_{user['user_id']}", use_container_width=True):
                        # This manually sets is_premium to 0
                        db.downgrade_to_basic(user['user_id'])
                        st.rerun()
                
                st.markdown("---")


            # --- Payment Management ---
            st.markdown("##### Pending Payments Table")
            payments = db.get_pending_payments()
            if payments:
                payments_df = pd.DataFrame(payments)
                payments_df['timestamp'] = pd.to_datetime(payments_df['timestamp']).dt.strftime('%Y-%m-%d %H:%M')
                st.dataframe(payments_df[['id', 'user_id', 'phone', 'mpesa_code', 'timestamp']], hide_index=True, use_container_width=True)
                
                # Approval buttons for pending payments
                st.markdown("###### Approve Payments")
                for p in payments:
                    col_p1, col_p2, col_p3, col_p4 = st.columns([1, 1, 2, 2])
                    with col_p1:
                        st.caption(f"ID: {p['id']}")
                    with col_p2:
                        st.caption(f"User: {p['user_id']}")
                    with col_p3:
                        st.write(f"Phone: {p['phone']} | Code: {p['mpesa_code']}")
                    with col_p4:
                        if st.button("✅ Approve Payment (Grant Premium)", key=f"approve_{p['id']}", use_container_width=True, type="primary"):
                            db.approve_payment(p["id"])
                            st.rerun()
                st.markdown("---")
            else:
                st.info("No pending payments requiring approval.")

# Final catch-all to ensure redirection if somehow session state is broken
else:
    if st.session_state.page != "landing":
        st.session_state.page = "landing"
        st.rerun()
