# ai_engine.py
import json
import time
import requests
from streamlit import cache_data
from typing import List, Dict
import fitz  # PyMuPDF - pip install pymupdf

# ==============================================================================
# API CONFIGURATION
# ==============================================================================

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models/"

# Chat / streaming – stable, fast, free tier
GEMINI_CHAT_MODEL = "gemini-2.5-flash"

# Structured JSON (exam, grading) – reliable fallback
GEMINI_STRUCTURED_MODEL = "gemini-1.5-flash"

# ==============================================================================
# AI ENGINE CLASS
# ==============================================================================

class AIEngine:
    def __init__(self, gemini_key: str, hf_key: str = ""):
        self.gemini_key = gemini_key or ""
        self.hf_key = hf_key or ""  # Not used anymore, but kept for compatibility
        # No HF headers needed

    # --------------------------------------------------------------------------
    # Low-level request with back-off + detailed logging
    # --------------------------------------------------------------------------
    def _api_call(self, url: str, payload: dict, headers: dict | None = None,
                  params: dict | None = None, stream: bool = False, max_retries: int = 5):
        headers = headers or {"Content-Type": "application/json"}
        params = params or {}
        if self.gemini_key and "key" not in params:
            params["key"] = self.gemini_key

        for attempt in range(max_retries):
            try:
                resp = requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    params=params,
                    timeout=60,
                    stream=stream,
                )
                resp.raise_for_status()
                return resp
            except requests.exceptions.HTTPError as e:
                err = resp.text
                if resp.status_code == 404:
                    print("[404] Model not found – check model name")
                elif resp.status_code == 400:
                    print("[400] Bad request – check payload")
                print(f"Error: {err}")
                if attempt == max_retries - 1:
                    raise Exception(f"API error {resp.status_code}: {err}")
                time.sleep(2 ** attempt)
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise Exception(f"Request failed: {e}")
                time.sleep(2 ** attempt)

    # --------------------------------------------------------------------------
    # PDF → TEXT (LOCAL with PyMuPDF) – NO HF, NO INTERNET
    # --------------------------------------------------------------------------
    @cache_data(ttl="2h", show_spinner="Extracting PDF…")
    def extract_text_from_pdf(_self, pdf_bytes: bytes) -> str:
        """Extract text locally using PyMuPDF – works offline & in production."""
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            text = ""
            for page in doc:
                text += page.get_text("text") + "\n"
            doc.close()
            return text.strip() or "No text extracted from the PDF."
        except Exception as e:
            return f"PDF extraction error: {e}"

    # --------------------------------------------------------------------------
    # GEMINI – CHAT / Q&A (stable 2.5) – ROBUST + DEBUG
    # --------------------------------------------------------------------------
    def generate_response_gemini(self, contents: List[Dict], system_prompt: str,
                                 use_grounding: bool = False) -> str:
        payload = {
            "contents": contents,
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "generationConfig": {
                "maxOutputTokens": 4096,
                "temperature": 0.7
            },
            "safetySettings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
            ]
        }
        if use_grounding:
            payload["tools"] = [{"google_search": {}}]

        url = f"{GEMINI_API_BASE}{GEMINI_CHAT_MODEL}:generateContent"
        try:
            r = self._api_call(url, payload)
            data = r.json()
            print("=== GEMINI FULL RESPONSE ===")
            print(json.dumps(data, indent=2))
            print("==============================")

            candidate = data.get("candidates", [{}])[0]
            parts = candidate.get("content", {}).get("parts", [])
            text = parts[0].get("text", "") if parts else ""

            if not text:
                finish_reason = candidate.get("finishReason", "UNKNOWN")
                print(f"Empty response – finishReason: {finish_reason}")
                return "The AI didn't return an answer. Try rephrasing."

            return text
        except Exception as e:
            print(f"Gemini chat error: {e}")
            return "Sorry, the AI could not answer right now. (Check console.)"

    # --------------------------------------------------------------------------
    # PUBLIC HELPERS
    # --------------------------------------------------------------------------
    def generate_response(self, user_query: str, system_prompt: str) -> str:
        """Single-turn chat."""
        contents = [{"role": "user", "parts": [{"text": user_query}]}]
        return self.generate_response_gemini(contents, system_prompt)

    def stream_response(self, user_query: str, system_prompt: str):
        """Streaming chat – falls back to non-stream if needed."""
        if not self.gemini_key:
            mock = f"Hint for «{user_query[:30]}…» – think step-by-step."
            for i in range(0, len(mock), 12):
                yield mock[i:i + 12]
            return

        full = self.generate_response(user_query, system_prompt)
        for chunk in [full[i:i + 50] for i in range(0, len(full), 50)]:
            yield chunk

    # --------------------------------------------------------------------------
    # EXAM / GRADING / SUMMARY (Optional – keep or remove)
    # --------------------------------------------------------------------------
    def generate_exam_questions(self, subject, exam_type, num_questions):
        return [
            {
                "question": f"What is a core idea in {subject}?",
                "options": ["A) …", "B) …", "C) …", "D) …"],
                "correct_answer": "B) …",
            }
        ][:num_questions]

    def grade_short_answer(self, question, model_answer, user_answer):
        is_correct = len(user_answer) > 15
        feedback = "Correct!" if is_correct else "Add more detail."
        return {"is_correct": is_correct, "feedback": feedback}

    def summarize_text_hf(self, text: str) -> str:
        return "Summary not available (HF disabled)."
