# mpesa_auth.py
import base64
import toml
import requests
from pathlib import Path

# ----------------------------------------------------------------------
# Load credentials from TOML (keeps secrets out of code)
# ----------------------------------------------------------------------
CONFIG_PATH = Path(__file__).with_name("mpesa_config.toml")
if not CONFIG_PATH.is_file():
    raise FileNotFoundError(f"Missing {CONFIG_PATH}. Create it with your Daraja keys.")

cfg = toml.load(CONFIG_PATH)
KEY    = cfg["mpesa"]["daraja"]["consumer_key"]
SECRET = cfg["mpesa"]["daraja"]["consumer_secret"]

# ----------------------------------------------------------------------
# Build Basic Auth header (once – reusable)
# ----------------------------------------------------------------------
def _basic_auth_header() -> str:
    auth_str = f"{KEY}:{SECRET}"
    b64 = base64.b64encode(auth_str.encode()).decode()
    return f"Basic {b64}"

# ----------------------------------------------------------------------
# Get OAuth token (sandbox)
# ----------------------------------------------------------------------
def get_oauth_token() -> str:
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    headers = {"Authorization": _basic_auth_header()}

    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()               # will raise HTTPError on 4xx/5xx

    token = resp.json()["access_token"]
    expires_in = resp.json().get("expires_in", 3600)
    print(f"[DARAJA] Token received – expires in {expires_in}s")
    return token

# ----------------------------------------------------------------------
# Quick test when run directly
# ----------------------------------------------------------------------
if __name__ == "__main__":
    try:
        token = get_oauth_token()
        print("Bearer token:", token)
    except Exception as e:
        print("Failed to get token:", e)
