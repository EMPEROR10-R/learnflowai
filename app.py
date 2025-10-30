import streamlit as st
import os
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
from database import Database
from ai_engine import AIEngine, cached_ai_response
from utils import PDFParser, Translator_Utils, EssayGrader, VoiceInputHelper, cached_pdf_extract
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES
from stripe_premium import StripePremium, show_premium_upgrade_banner, show_premium_benefits
import json
import time

st.set_page_config(
    page_title="LearnFlow AI - Your Personal AI Tutor",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @keyframes fadeInDown {
        from {
            opacity: 0;
            transform: translateY(-30px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    @keyframes slideInLeft {
        from {
            opacity: 0;
            transform: translateX(-50px);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }
    
    @keyframes slideInRight {
        from {
            opacity: 0;
            transform: translateX(50px);
        }
        to {
            opacity: 1;
            transform: translateX(0);
        }
    }
    
    @keyframes pulse {
        0%, 100% {
            transform: scale(1);
        }
        50% {
            transform: scale(1.05);
        }
    }
    
    @keyframes glow {
        0%, 100% {
            box-shadow: 0 0 5px rgba(102, 126, 234, 0.5);
        }
        50% {
            box-shadow: 0 0 20px rgba(102, 126, 234, 0.8);
        }
    }
    
    @keyframes gradient-shift {
        0% {
            background-position: 0% 50%;
        }
        50% {
            background-position: 100% 50%;
        }
        100% {
            background-position: 0% 50%;
        }
    }
    
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #667eea 100%);
        background-size: 200% 200%;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 1rem;
        animation: fadeInDown 1s ease-out, gradient-shift 3s ease infinite;
    }
    
    .chat-message-user {
        background-color: #E3F2FD;
        padding: 15px;
        border-radius: 15px;
        margin: 10px 0;
        border-left: 4px solid #2196F3;
        animation: slideInRight 0.5s ease-out;
        transition: transform 0.2s ease;
    }
    
    .chat-message-user:hover {
        transform: translateX(-5px);
    }
    
    .chat-message-ai {
        background-color: #E8F5E9;
        padding: 15px;
        border-radius: 15px;
        margin: 10px 0;
        border-left: 4px solid #4CAF50;
        animation: slideInLeft 0.5s ease-out;
        transition: transform 0.2s ease;
    }
    
    .chat-message-ai:hover {
        transform: translateX(5px);
    }
    
    .streak-badge {
        display: inline-block;
        padding: 5px 15px;
        background: linear-gradient(135deg, #FF6B6B 0%, #FFE66D 100%);
        border-radius: 20px;
        color: white;
        font-weight: bold;
        margin: 5px;
        animation: pulse 2s ease-in-out infinite;
        transition: transform 0.3s ease;
    }
    
    .streak-badge:hover {
        transform: scale(1.1) rotate(5deg);
    }
    
    .premium-badge {
        background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%);
        padding: 3px 10px;
        border-radius: 10px;
        color: white;
        font-size: 0.8rem;
        font-weight: bold;
        animation: glow 2s ease-in-out infinite;
    }
    
    .stButton>button {
        width: 100%;
        transition: all 0.3s ease;
    }
    
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
    }
    
    .stTab {
        transition: all 0.3s ease;
    }
    
    .welcome-animation {
        animation: fadeInDown 1.2s ease-out;
    }
    
    .metric-card {
        animation: fadeInDown 0.8s ease-out;
        transition: transform 0.3s ease;
    }
    
    .metric-card:hover {
        transform: translateY(-5px);
    }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_database():
    return Database()

@st.cache_resource
def init_translator():
    return Translator_Utils()

def init_session_state():
    if 'user_id' not in st.session_state:
        db = init_database()
        st.session_state.user_id = db.create_user()
    
    if 'chat_history' not in st.session_state:
        st.session_state.chat_history = []
    
    if 'current_subject' not in st.session_state:
        st.session_state.current_subject = "General"
    
    if 'groq_api_key' not in st.session_state:
        st.session_state.groq_api_key = ""
    
    if 'language' not in st.session_state:
        st.session_state.language = 'en'
    
    if 'show_voice_button' not in st.session_state:
        st.session_state.show_voice_button = True

def check_and_update_streak():
    db = init_database()
    streak = db.update_streak(st.session_state.user_id)
    
    if streak == 3:
        db.add_badge(st.session_state.user_id, "streak_3")
    elif streak == 7:
        db.add_badge(st.session_state.user_id, "streak_7")
    elif streak == 30:
        db.add_badge(st.session_state.user_id, "streak_30")
    
    return streak

def check_premium_limits(db: Database, user_id: str) -> dict:
    is_premium = db.check_premium(user_id)
    
    if is_premium:
        return {
            'can_query': True,
            'can_upload_pdf': True,
            'queries_left': 'Unlimited',
            'pdfs_left': 'Unlimited',
            'is_premium': True
        }
    
    daily_queries = db.get_daily_query_count(user_id)
    daily_pdfs = db.get_pdf_count_today(user_id)
    
    return {
        'can_query': daily_queries < 10,
        'can_upload_pdf': daily_pdfs < 1,
        'queries_left': max(0, 10 - daily_queries),
        'pdfs_left': max(0, 1 - daily_pdfs),
        'is_premium': False
    }

def sidebar_config():
    with st.sidebar:
        st.markdown('<p class="main-header">🎓 LearnFlow AI</p>', unsafe_allow_html=True)
        
        db = init_database()
        user = db.get_user(st.session_state.user_id)
        limits = check_premium_limits(db, st.session_state.user_id)
        
        if limits['is_premium']:
            st.markdown('<span class="premium-badge">💎 PREMIUM</span>', unsafe_allow_html=True)
        
        streak = check_and_update_streak()
        st.markdown(f'<span class="streak-badge">🔥 {streak} Day Streak</span>', unsafe_allow_html=True)
        
        if user:
            badges = json.loads(user['badges'])
            if badges:
                st.write("**Badges:**")
                badge_display = " ".join([BADGES.get(b, b) for b in badges[:5]])
                st.write(badge_display)
        
        st.markdown("---")
        
        st.markdown("### ⚙️ Settings")
        
        api_key = st.text_input(
            "Groq API Key (Free)",
            type="password",
            value=st.session_state.groq_api_key,
            help="Get your free API key from https://console.groq.com"
        )
        if api_key != st.session_state.groq_api_key:
            st.session_state.groq_api_key = api_key
        
        if not api_key:
            st.info("📝 Add your free Groq API key to unlock AI tutoring!")
            st.markdown("[Get Free API Key →](https://console.groq.com)")
        
        st.markdown("---")
        
        st.markdown("### 📚 Subject")
        subjects = list(SUBJECT_PROMPTS.keys())
        st.session_state.current_subject = st.selectbox(
            "Choose your subject",
            subjects,
            index=subjects.index(st.session_state.current_subject) if st.session_state.current_subject in subjects else 0
        )
        
        st.markdown("---")
        
        st.markdown("### 🌍 Language")
        translator = init_translator()
        lang_options = {v: k for k, v in translator.supported_languages.items()}
        selected_lang = st.selectbox(
            "Interface Language",
            list(lang_options.keys()),
            index=0
        )
        st.session_state.language = lang_options[selected_lang]
        
        st.markdown("---")
        
        if not limits['is_premium']:
            st.markdown("### 📊 Daily Limits (Free Tier)")
            st.metric("AI Queries Left", f"{limits['queries_left']}/10")
            st.metric("PDF Uploads Left", f"{limits['pdfs_left']}/1")
            
            if st.button("🚀 Upgrade to Premium", type="primary"):
                st.session_state.show_premium = True
        
        st.markdown("---")
        st.caption(f"Powered by {AIEngine(st.session_state.groq_api_key).get_engine_name()}")
        st.caption("100% Free • No Credit Card")

def main_chat_interface():
    db = init_database()
    limits = check_premium_limits(db, st.session_state.user_id)
    
    st.markdown(f'<h1 class="main-header">💬 {st.session_state.current_subject} Tutor</h1>', unsafe_allow_html=True)
    
    for idx, msg in enumerate(st.session_state.chat_history):
        if msg['role'] == 'user':
            st.markdown(f'<div class="chat-message-user"><strong>You:</strong> {msg["content"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="chat-message-ai"><strong>AI Tutor:</strong> {msg["content"]}</div>', unsafe_allow_html=True)
    
    user_question = st.text_area(
        "Ask your question (I'll guide you with hints, not direct answers):",
        height=100,
        key="user_input",
        placeholder="Example: I'm stuck on this algebra problem... Can you help me understand how to approach it?"
    )
    
    col_voice1, col_voice2 = st.columns([1, 1])
    with col_voice1:
        try:
            voice_input = st.audio_input("🎤 Or use voice input (click to record)", key="voice_recorder")
            if voice_input:
                st.info("Voice recorded! Processing audio... (Note: transcription requires additional API setup)")
                st.session_state.voice_used = True
        except Exception as e:
            if st.button("🎤 Voice Input (Web Speech API)", help="Use browser voice input"):
                import streamlit.components.v1 as components
                components.html("""
                    <button onclick="startVoiceRecognition()" style="
                        padding: 10px 20px;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                        border: none;
                        border-radius: 10px;
                        cursor: pointer;
                        font-size: 16px;
                    ">🎤 Click to Speak</button>
                    
                    <script>
                    function startVoiceRecognition() {
                        if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
                            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
                            const recognition = new SpeechRecognition();
                            recognition.continuous = false;
                            recognition.interimResults = false;
                            recognition.lang = 'en-US';
                            
                            recognition.onresult = function(event) {
                                const transcript = event.results[0][0].transcript;
                                alert('You said: ' + transcript + '\\n\\nPlease type this into the text box above.');
                            };
                            
                            recognition.onerror = function(event) {
                                alert('Voice recognition error: ' + event.error);
                            };
                            
                            recognition.start();
                        } else {
                            alert('Voice recognition is not supported in your browser. Please use Chrome or Edge.');
                        }
                    }
                    </script>
                """, height=60)
    
    if st.button("📤 Send Question", type="primary"):
        if user_question.strip():
            if not limits['can_query']:
                st.error("🚫 Daily query limit reached! Upgrade to Premium for unlimited queries.")
                show_premium_upgrade_banner()
                return
            
            st.session_state.chat_history.append({
                'role': 'user',
                'content': user_question
            })
            
            with st.spinner("🤔 Thinking..."):
                ai_engine = AIEngine(st.session_state.groq_api_key)
                
                system_prompt = get_enhanced_prompt(
                    st.session_state.current_subject,
                    user_question,
                    f"Previous conversation: {len(st.session_state.chat_history)} messages"
                )
                
                response_placeholder = st.empty()
                full_response = ""
                
                for chunk in ai_engine.stream_response(user_question, system_prompt):
                    full_response += chunk
                    response_placeholder.markdown(f'<div class="chat-message-ai"><strong>AI Tutor:</strong> {full_response}</div>', unsafe_allow_html=True)
                
                st.session_state.chat_history.append({
                    'role': 'assistant',
                    'content': full_response
                })
                
                db.add_chat_history(
                    st.session_state.user_id,
                    st.session_state.current_subject,
                    user_question,
                    full_response
                )
                db.update_user_activity(st.session_state.user_id)
                
                if len(st.session_state.chat_history) == 2:
                    db.add_badge(st.session_state.user_id, "first_question")
                    st.balloons()
                
                st.rerun()

def pdf_upload_tab():
    db = init_database()
    limits = check_premium_limits(db, st.session_state.user_id)
    
    st.markdown("### 📄 Upload Your Notes/PDFs")
    st.write("Upload your study materials and I'll help explain the content!")
    
    if not limits['can_upload_pdf']:
        st.warning("🚫 Daily PDF upload limit reached!")
        show_premium_upgrade_banner()
        return
    
    uploaded_file = st.file_uploader("Choose a PDF file", type=['pdf'])
    
    if uploaded_file:
        file_bytes = uploaded_file.read()
        
        with st.spinner("📖 Reading your PDF..."):
            text = cached_pdf_extract(file_bytes, uploaded_file.name)
        
        if text:
            st.success(f"✅ Successfully extracted {len(text)} characters from {uploaded_file.name}")
            
            with st.expander("📄 PDF Content Preview"):
                st.text(text[:1000] + "..." if len(text) > 1000 else text)
            
            db.add_pdf_upload(st.session_state.user_id, uploaded_file.name)
            db.add_badge(st.session_state.user_id, "pdf_explorer")
            
            question = st.text_area("What would you like to know about this content?")
            
            if st.button("🤔 Ask about this PDF"):
                if question:
                    with st.spinner("Analyzing..."):
                        ai_engine = AIEngine(st.session_state.groq_api_key)
                        
                        prompt = f"""Based on this document content:

{text[:2000]}

Student question: {question}

Provide a Socratic response that guides the student to understand the content."""
                        
                        system_prompt = get_enhanced_prompt(st.session_state.current_subject, question)
                        
                        response = ai_engine.generate_response(prompt, system_prompt)
                        
                        st.markdown(f'<div class="chat-message-ai"><strong>AI Tutor:</strong> {response}</div>', unsafe_allow_html=True)
                        
                        db.add_chat_history(st.session_state.user_id, "PDF Analysis", question, response)

def progress_dashboard_tab():
    db = init_database()
    
    st.markdown("### 📊 Your Learning Progress")
    
    user = db.get_user(st.session_state.user_id)
    
    if user:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Questions", user['total_queries'])
        
        with col2:
            st.metric("Current Streak", f"{user['streak_days']} days")
        
        with col3:
            badges = json.loads(user['badges'])
            st.metric("Badges Earned", len(badges))
        
        with col4:
            status = "Premium 💎" if db.check_premium(st.session_state.user_id) else "Free Tier"
            st.metric("Account Status", status)
        
        st.markdown("---")
        
        progress_stats = db.get_progress_stats(st.session_state.user_id)
        
        if progress_stats:
            st.markdown("### 📈 Subject Performance")
            
            subjects = [stat['subject'] for stat in progress_stats]
            confidence = [stat['avg_confidence'] for stat in progress_stats]
            topics = [stat['topics_covered'] for stat in progress_stats]
            
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=subjects,
                y=confidence,
                name='Avg Confidence',
                marker_color='rgb(102, 126, 234)'
            ))
            
            fig.update_layout(
                title='Average Confidence by Subject',
                xaxis_title='Subject',
                yaxis_title='Confidence Level',
                yaxis=dict(range=[0, 5])
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            fig2 = px.pie(
                values=topics,
                names=subjects,
                title='Topics Covered by Subject'
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("📚 Start learning to see your progress here!")
        
        quiz_history = db.get_quiz_history(st.session_state.user_id)
        
        if quiz_history:
            st.markdown("### 🎯 Recent Quiz Scores")
            
            quiz_data = []
            for quiz in quiz_history[:5]:
                percentage = (quiz['score'] / quiz['total_questions']) * 100
                quiz_data.append({
                    'Exam': quiz['exam_type'],
                    'Subject': quiz['subject'],
                    'Score': f"{quiz['score']}/{quiz['total_questions']}",
                    'Percentage': f"{percentage:.1f}%",
                    'Date': quiz['completed_at']
                })
            
            st.table(quiz_data)

def exam_mode_tab():
    db = init_database()
    limits = check_premium_limits(db, st.session_state.user_id)
    
    st.markdown("### 🎓 Exam Preparation Mode")
    st.write("Practice with timed quizzes for SAT, ACT, GCSE, and more!")
    
    exam_type = st.selectbox("Select Exam Type", list(EXAM_TYPES.keys()))
    
    exam_info = EXAM_TYPES[exam_type]
    subject = st.selectbox("Select Subject", exam_info['subjects'])
    
    st.info(f"⏱️ Time: {exam_info['time_per_section']} minutes | 📝 Questions: {exam_info['question_count']}")
    
    if st.button("🚀 Start Practice Quiz"):
        if not limits['can_query']:
            st.error("🚫 Daily query limit reached! Upgrade to Premium for unlimited practice.")
            return
        
        st.session_state.quiz_active = True
        st.session_state.quiz_start_time = datetime.now()
        st.session_state.quiz_questions = []
        
        with st.spinner("Generating practice questions..."):
            ai_engine = AIEngine(st.session_state.groq_api_key)
            
            prompt = f"""Generate {min(5, exam_info['question_count'])} {exam_type} {subject} practice questions.
            
Format each question with:
1. The question
2. Four answer choices (A, B, C, D)
3. A brief hint (Socratic style)

Make them challenging but appropriate for {exam_type} level."""
            
            response = ai_engine.generate_response(prompt, max_tokens=2000)
            
            st.markdown("### 📝 Practice Questions")
            st.markdown(response)
            
            score = st.slider("How many did you get right?", 0, 5, 0)
            
            if st.button("Submit Score"):
                db.add_quiz_result(st.session_state.user_id, subject, exam_type, score, 5)
                
                percentage = (score / 5) * 100
                
                if percentage >= 80:
                    st.success(f"🎉 Excellent! You scored {percentage:.0f}%")
                    db.add_badge(st.session_state.user_id, "quiz_ace")
                elif percentage >= 60:
                    st.info(f"👍 Good work! You scored {percentage:.0f}%")
                else:
                    st.warning(f"Keep practicing! You scored {percentage:.0f}%")
                
                st.balloons()

def essay_grader_tab():
    st.markdown("### ✍️ AI Essay Grader")
    st.write("Submit your essay for instant feedback and scoring!")
    
    essay_text = st.text_area(
        "Paste your essay here:",
        height=300,
        placeholder="Write or paste your essay here..."
    )
    
    if st.button("📊 Grade My Essay"):
        if essay_text.strip():
            with st.spinner("Analyzing your essay..."):
                grader = EssayGrader()
                results = grader.grade_essay(essay_text)
                
                st.markdown("### 📈 Essay Analysis Results")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.metric("Total Score", f"{results['total_score']}/100")
                    st.write(f"**{results['overall']}**")
                
                with col2:
                    st.write("**Breakdown:**")
                    for category, score in results['breakdown'].items():
                        st.write(f"- {category.title()}: {score}")
                
                st.markdown("### 📊 Statistics")
                stats_col1, stats_col2, stats_col3 = st.columns(3)
                
                with stats_col1:
                    st.metric("Word Count", results['stats']['word_count'])
                
                with stats_col2:
                    st.metric("Sentences", results['stats']['sentence_count'])
                
                with stats_col3:
                    st.metric("Paragraphs", results['stats']['paragraph_count'])
                
                if results['feedback']:
                    st.markdown("### 💡 Feedback")
                    for item in results['feedback']:
                        st.write(f"- {item}")
        else:
            st.warning("Please enter some text to grade!")

def premium_tab():
    st.markdown("### 💎 Premium Subscription")
    
    show_premium_benefits()
    
    st.markdown("---")
    
    db = init_database()
    is_premium = db.check_premium(st.session_state.user_id)
    
    if is_premium:
        st.success("✅ You are a Premium member!")
        st.write("Enjoy unlimited access to all premium features!")
        
        stripe_api_key = st.session_state.get('stripe_api_key', '')
        if stripe_api_key:
            st.info("💳 Manage your subscription")
            if st.button("🔧 Manage Billing", type="secondary"):
                stripe_handler = StripePremium(stripe_api_key)
                st.info("Customer portal link would appear here when fully configured.")
        else:
            st.info("To manage your subscription, contact support or configure Stripe API key.")
    else:
        st.markdown("### 🚀 Ready to Upgrade?")
        st.write("For just $4.99/month, unlock unlimited learning potential!")
        
        stripe_api_key = st.text_input(
            "Stripe API Key (Optional - for live payments)",
            type="password",
            help="Add your Stripe secret key to enable real payments",
            key="stripe_key_input"
        )
        
        if stripe_api_key:
            st.session_state.stripe_api_key = stripe_api_key
            
            col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
            with col_btn2:
                if st.button("💳 Subscribe Now - $4.99/month", type="primary", use_container_width=True):
                    try:
                        stripe_handler = StripePremium(stripe_api_key)
                        
                        base_url = "https://yourapp.streamlit.app"
                        session_data = stripe_handler.create_checkout_session(
                            st.session_state.user_id,
                            f"{base_url}?success=1",
                            f"{base_url}?cancel=1"
                        )
                        
                        if session_data:
                            st.success("✅ Checkout session created!")
                            st.markdown(f"[Click here to complete payment →]({session_data['url']})")
                        else:
                            st.error("Failed to create checkout session. Please check your Stripe configuration.")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
        else:
            st.info("""
            **To activate Premium subscriptions:**
            
            1. Get a Stripe API key from https://stripe.com
            2. Enter your Stripe secret key above
            3. Click "Subscribe Now" to create checkout session
            4. The complete Stripe integration is ready in `stripe_premium.py`
            
            **Demo Mode:** The app works fully without Stripe (with free tier limits).
            Add Stripe only when you're ready to accept real payments!
            """)
            
            col_demo1, col_demo2, col_demo3 = st.columns([1, 2, 1])
            with col_demo2:
                if st.button("🎭 Simulate Premium Upgrade (Demo)", type="secondary", use_container_width=True):
                    st.info("Demo: In production, this would redirect to Stripe Checkout!")
                    st.balloons()
        
        st.markdown("### 💰 Revenue Potential")
        
        users = st.slider("Estimated Premium Users", 100, 10000, 1000, 100)
        monthly_revenue = users * 4.99
        annual_revenue = monthly_revenue * 12
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Monthly Revenue", f"${monthly_revenue:,.2f}")
        
        with col2:
            st.metric("Annual Revenue", f"${annual_revenue:,.2f}")

def show_welcome_animation():
    if 'show_welcome' not in st.session_state:
        st.session_state.show_welcome = True
    
    if st.session_state.show_welcome:
        st.markdown("""
        <div class="welcome-animation" style="
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 40px;
            border-radius: 20px;
            text-align: center;
            color: white;
            margin: 20px 0;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        ">
            <h1 style="font-size: 3rem; margin: 0; animation: fadeInDown 1s ease-out;">
                🎓 Welcome to LearnFlow AI
            </h1>
            <p style="font-size: 1.5rem; margin: 20px 0; animation: fadeInDown 1.2s ease-out;">
                Your Personal AI Learning Tutor
            </p>
            <p style="font-size: 1.1rem; animation: fadeInDown 1.4s ease-out;">
                Ask anything • Upload notes • Get hints • Never cheat
            </p>
            <div style="margin-top: 30px; animation: fadeInDown 1.6s ease-out;">
                <span style="
                    display: inline-block;
                    background: rgba(255,255,255,0.2);
                    padding: 10px 20px;
                    border-radius: 10px;
                    margin: 5px;
                ">✨ 100% Free</span>
                <span style="
                    display: inline-block;
                    background: rgba(255,255,255,0.2);
                    padding: 10px 20px;
                    border-radius: 10px;
                    margin: 5px;
                ">🚀 AI-Powered</span>
                <span style="
                    display: inline-block;
                    background: rgba(255,255,255,0.2);
                    padding: 10px 20px;
                    border-radius: 10px;
                    margin: 5px;
                ">🌍 Multilingual</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            if st.button("🚀 Start Learning!", type="primary", use_container_width=True):
                st.session_state.show_welcome = False
                st.rerun()

def main():
    init_session_state()
    
    query_params = st.query_params
    if 'success' in query_params:
        st.success("🎉 Payment successful! Your Premium subscription is being activated...")
        st.info("""
        **Next Steps:**
        1. Stripe webhook will confirm your payment
        2. Your account will be upgraded to Premium
        3. Enjoy unlimited features!
        
        Note: In production, implement Stripe webhooks to automatically upgrade users.
        See `stripe_premium.py` for webhook handling code.
        """)
        st.balloons()
    
    if 'cancel' in query_params:
        st.warning("Payment was cancelled. You can try again anytime from the Premium tab!")
    
    if st.session_state.get('show_welcome', True):
        show_welcome_animation()
        return
    
    sidebar_config()
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "💬 Chat Tutor",
        "📄 PDF Upload",
        "📊 Progress",
        "🎓 Exam Prep",
        "✍️ Essay Grader",
        "💎 Premium"
    ])
    
    with tab1:
        main_chat_interface()
    
    with tab2:
        pdf_upload_tab()
    
    with tab3:
        progress_dashboard_tab()
    
    with tab4:
        exam_mode_tab()
    
    with tab5:
        essay_grader_tab()
    
    with tab6:
        premium_tab()
    
    st.markdown("---")
    st.caption("LearnFlow AI - Learn Smarter, Not Harder | 100% Free Core Features")
    st.caption("Built with Streamlit + Groq + SQLite | Open Source")

if __name__ == "__main__":
    main()
