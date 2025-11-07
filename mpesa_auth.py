# mpesa_auth.py
import requests
import base64
from datetime import datetime
import streamlit as st

def get_oauth_token():
    consumer_key = st.secrets["MPESA_CONSUMER_KEY"]
    consumer_secret = st.secrets["MPESA_CONSUMER_SECRET"]
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    try:
        response = requests.get(url, auth=(consumer_key, consumer_secret))
        response.raise_for_status()
        return response.json()["access_token"]
    except Exception as e:
        raise ValueError(f"Failed to get OAuth token: {e}")

def stk_push(phone: str, amount: int, account_ref: str = "LearnFlowAI", desc: str = "Premium Upgrade"):
    token = get_oauth_token()
    url = "https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    headers = {"Authorization": f"Bearer {token}"}

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    shortcode = st.secrets.get("MPESA_SHORTCODE", "174379")
    passkey = st.secrets["MPESA_PASSKEY"]
    password_str = f"{shortcode}{passkey}{timestamp}"
    password = base64.b64encode(password_str.encode()).decode("utf-8")

    # REPLACE WITH YOUR NGROK/PUBLIC URL + /callback
    callback_url = "https://your-ngrok-url.ngrok.io/callback"

    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone,
        "PartyB": shortcode,
        "PhoneNumber": phone,
        "CallBackURL": callback_url,
        "AccountReference": account_ref,
        "TransactionDesc": desc
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise ValueError(f"STK Push failed: {e}")
