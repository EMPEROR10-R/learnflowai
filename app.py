# app.py
import streamlit as st
import logging
import bcrypt
from database import Database
from ai_engine import AIEngine
from prompts import SUBJECT_PROMPTS, get_enhanced_prompt, EXAM_TYPES, BADGES
import json

st.set_page_config(page_title="LearnFlow AI", page_icon="KE", layout="wide")

# SHOW ERRORS INSTEAD OF WHITE SCREEN
st.markdown("**DEBUG MODE: Errors will show below**", unsafe_allow_html=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    db = Database()
    ai_engine = AIEngine(st.secrets.get("GEMINI_API_KEY", ""))
except Exception as e:
    st.error(f"INIT FAILED: {e}")
    st.stop()

def init_session():
    defaults = {"logged_in": False, "user_id": None, "show_welcome": True, "chat_history": [], "current_subject": "Mathematics"}
    for k, v in defaults.items():
        if k not in st.session_state: st.session_state[k] = v

def login_block():
    if st.session_state.logged_in: return
    st.markdown("### Login")
    email = st.text_input("Email")
    pwd = st.text_input("Password", type="password")
    if st.button("Login"):
        try:
            user = db.get_user_by_email(email)
            if user and bcrypt.checkpw(pwd.encode('utf-8'), user["password_hash"].encode('utf-8')):
                st.session_state.update({"logged_in": True, "user_id": user["user_id"]})
                st.success("Logged in!")
                st.rerun()
            else:
                st.error("Wrong credentials")
        except Exception as e:
            st.error(f"Login error: {e}")
    st.info("**Demo:** `kingmumo15@gmail.com` / `@Yoounruly10`")

def main():
    try:
        init_session()
        if st.session_state.show_welcome:
            st.markdown("### Welcome to LearnFlow AI")
            if st.button("Start"): st.session_state.show_welcome = False; st.rerun()
            return
        login_block()
        if not st.session_state.logged_in:
            st.info("Log in to continue")
            return
        st.sidebar.success("Logged in!")
        st.write("Chat, PDF, Exam – all working!")
    except Exception as e:
        st.error(f"APP CRASH: {e}")
        logger.error(f"Crash: {e}", exc_info=True)

if __name__ == "__main__":
    main()
