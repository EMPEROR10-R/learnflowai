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
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        margin-bottom: 1rem;
    }
    .chat-message-user {
        background-color: #E3F2FD;
        padding: 15px;
        border-radius: 15px;
        margin: 10px 0;
        border-left: 4px solid #2196F3;
    }
    .chat-message-ai {
        background-color: #E8F5E9;
        padding: 15px;
        border-radius: 15px;
        margin: 10px 0;
        border-left: 4px solid #4CAF50;
    }
    .streak-badge {
        display: inline-block;
        padding: 5px 15px;
        background: linear-gradient(135deg, #FF6B6B 0%, #FFE66D 100%);
        border-radius: 20px;
        color: white;
        font-weight: bold;
        margin: 5px;
    }
    .premium-badge {
        background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%);
        padding: 3px 10px;
        border-radius: 10px;
        color: white;
        font-size: 0.8rem;
        font-weight: bold;
    }
    .stButton>button {
        width: 100%;
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
    
    col1, col2 = st.columns([5, 1])
    
    with col1:
        user_question = st.text_area(
            "Ask your question (I'll guide you with hints, not direct answers):",
            height=100,
            key="user_input",
            placeholder="Example: I'm stuck on this algebra problem... Can you help me understand how to approach it?"
        )
    
    with col2:
        st.write("")
        st.write("")
        if st.button("🎤 Voice", help="Use voice input (Chrome/Edge only)"):
            st.info("Voice input is available in supported browsers. Click and speak your question!")
    
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
        st.info("Premium subscription management is available when Stripe is configured.")
    else:
        st.markdown("### 🚀 Ready to Upgrade?")
        st.write("For just $4.99/month, unlock unlimited learning potential!")
        
        st.info("""
        **To activate Premium subscriptions:**
        
        1. Get a Stripe API key from https://stripe.com
        2. Configure it in the app settings
        3. Start accepting subscriptions!
        
        The complete Stripe integration code is ready in `stripe_premium.py`
        """)
        
        st.markdown("### 💰 Revenue Potential")
        
        users = st.slider("Estimated Premium Users", 100, 10000, 1000, 100)
        monthly_revenue = users * 4.99
        annual_revenue = monthly_revenue * 12
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Monthly Revenue", f"${monthly_revenue:,.2f}")
        
        with col2:
            st.metric("Annual Revenue", f"${annual_revenue:,.2f}")

def main():
    init_session_state()
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
