import streamlit as st
import sys

st.set_page_config(page_title="Secret Checker", layout="centered")

st.title("Streamlit Secret Checker")
st.markdown("This app attempts to read the `GEMINI_API_KEY` directly from `.streamlit/secrets.toml`.")

try:
    # Attempt to read the secret
    api_key = st.secrets.get("GEMINI_API_KEY")

    if api_key:
        st.success("✅ **SUCCESS!** The API Key was read by Streamlit.")
        st.write(f"Key starts with: `{api_key[:10]}...` (Length: {len(api_key)})")
        st.info("Since this check worked, the issue is likely a temporary environment or networking problem when `ai_engine.py` first runs.")
    else:
        st.error("❌ **FAILURE!** Key is None or empty string.")
        st.warning(f"This indicates a file path issue. Check that the file `secrets.toml` is inside the hidden folder `.streamlit` in the same directory as this script.")

except Exception as e:
    st.exception(f"An unexpected error occurred during secret reading: {e}")
    st.error("If you see this, there might be a problem with your Streamlit environment setup.")
