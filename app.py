# app.py — WHITE SCREEN KILLER (Cloud 2025)
import streamlit as st
import traceback

# ────────────────────────────── FORCE ERRORS TO SHOW ──────────────────────────────
def show_crash(e):
    st.error("🚨 CRASH DETAILS:")
    st.error(f"Type: {type(e).__name__}")
    st.error(f"Message: {e}")
    st.code(traceback.format_exc(), language="python")
    st.stop()  # Stop execution to show error

st.exception_handler = show_crash

st.set_page_config(page_title="LearnFlow AI", page_icon="🇰🇪", layout="wide")

# ────────────────────────────── TEST BLOCK ──────────────────────────────
st.markdown("# 🏆 LearnFlow AI – Loading Check")
st.success("✅ Streamlit loaded!")

# Test secrets
try:
    key = st.secrets.get("GEMINI_API_KEY", "MISSING")
    if key == "MISSING":
        st.error("❌ GEMINI_API_KEY not set in GitHub Secrets!")
        st.info("Go to GitHub → Settings → Secrets → Add GEMINI_API_KEY")
    else:
        st.success("✅ Secrets loaded!")
except Exception as e:
    st.error(f"❌ Secrets failed: {e}")

# Test imports
st.markdown("### Import Tests")
try:
    from database import Database
    db = Database()
    st.success("✅ Database OK")
except Exception as e:
    st.error(f"❌ Database failed: {e}")
    st.code(traceback.format_exc())

try:
    from ai_engine import AIEngine
    st.success("✅ AI Engine OK")
except Exception as e:
    st.error(f"❌ AI Engine failed: {e}")
    st.code(traceback.format_exc())

try:
    from prompts import SUBJECT_PROMPTS
    st.success(f"✅ Prompts OK ({len(SUBJECT_PROMPTS)} subjects)")
except Exception as e:
    st.error(f"❌ Prompts failed: {e}")

st.markdown("### Next Steps")
st.info("""
1. **If errors above:** Fix them (e.g., add GitHub Secret)
2. **No errors:** Replace with full app.py
3. **Push to GitHub** → Cloud auto-deploys
""")

st.button("Test Complete – Ready for Full App")
