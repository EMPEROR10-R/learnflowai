# app.py — FINAL CLOUD-PROOF VERSION
import streamlit as st

st.set_page_config(page_title="LearnFlow AI", page_icon="Kenya", layout="wide")

# Force error display
def show_error(e):
    st.error(f"CRASH: {e}")
    st.code(__import__('traceback').format_exc())
st.exception_handler = show_error

st.markdown("# LearnFlow AI")
st.success("App loaded successfully!")

# Test key imports
try:
    from database import Database
    db = Database()
    st.success("Database connected")
except Exception as e:
    st.error(f"DB failed: {e}")

try:
    from ai_engine import AIEngine
    key = st.secrets.get("GEMINI_API_KEY", "")
    ai = AIEngine(key) if key else None
    st.success("AI ready" if key else "AI disabled (no key)")
except Exception as e:
    st.error(f"AI failed: {e}")

st.info("Full app will load after this test passes.")
