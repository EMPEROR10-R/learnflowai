# callback.py
from flask import Flask, request, jsonify
import json
import logging
from database import Database

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
db = Database()

@app.route("/callback", methods=["POST"])
def handle_callback():
    try:
        data = request.json
        if not data:
            logging.warning("No data received")
            return jsonify({"status": "no data"}), 400

        callback = data.get("Body", {}).get("stkCallback", {})
        result_code = callback.get("ResultCode")
        checkout_id = callback.get("CheckoutRequestID")

        logging.info(f"Callback received: {checkout_id} | Code: {result_code}")

        if result_code == 0:
            items = callback.get("CallbackMetadata", {}).get("Item", [])
            amount = next((item["Value"] for item in items if item["Name"] == "Amount"), 0)
            phone = next((item["Value"] for item in items if item["Name"] == "PhoneNumber"), None)
            mpesa_ref = next((item["Value"] for item in items if item["Name"] == "MpesaReceiptNumber"), "N/A")

            pending = db.get_pending_payment(checkout_id)
            if pending:
                db.activate_premium(pending["user_id"], amount, mpesa_ref)
                db.clear_pending_payment(checkout_id)
                logging.info(f"PREMIUM ACTIVATED for user {pending['user_id']} | Ref: {mpesa_ref}")
            else:
                logging.warning(f"No pending payment for {checkout_id}")
        else:
            desc = callback.get("ResultDesc", "Unknown")
            logging.error(f"Payment failed: {desc} | {checkout_id}")
            db.clear_pending_payment(checkout_id)

        return jsonify({"status": "received"}), 200

    except Exception as e:
        logging.error(f"Callback error: {e}")
        return jsonify({"status": "error"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
