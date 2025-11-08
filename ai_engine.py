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
            return text.strip()
        except Exception as e:
            return f"Error extracting PDF: {e}"

    # --------------------------------------------------------------------------
    # GEMINI CHAT (NON-STREAMING)
    # --------------------------------------------------------------------------
    def generate_response_gemini(self, contents: List[Dict], system_prompt: str, use_grounding: bool = False) -> str:
        if not self.gemini_key:
            return "AI is not configured. Contact admin."

        payload = {
            "contents": contents,
            "generationConfig": {
                "responseMimeType": "text/plain",
                "maxOutputTokens": 4096,
                "temperature": 0.7
            },
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
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
    # ENHANCED: MULTIPLE-CHOICE QUIZ GENERATION
    # --------------------------------------------------------------------------
    def generate_mcq_questions(self, subject: str, num_questions: int = 5) -> List[Dict]:
        """
        Generate MCQ questions using Gemini.
        Returns list of dicts: question, options, correct_answer, feedback
        """
        prompt = f"""
Generate {num_questions} multiple-choice questions for {subject} (KCSE level).
Each question must have:
- 1 clear question
- 4 options (A, B, C, D) — exactly one correct
- Correct answer (e.g., "B")
- Brief feedback explaining why the correct answer is right and others wrong

Use Kenyan curriculum examples. Output **only valid JSON** like this:
[
  {{
    "question": "What is the capital of Kenya?",
    "options": ["A) Nairobi", "B) Mombasa", "C) Kisumu", "D) Nakuru"],
    "correct_answer": "A) Nairobi",
    "feedback": "Nairobi is the capital and largest city of Kenya."
  }}
]
"""
        try:
            response = self.generate_response(prompt, "You are a quiz generator. Output only JSON.")
            # Clean and parse
            json_str = response.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:-3]
            elif json_str.startswith("```"):
                json_str = json_str[3:-3]
            questions = json.loads(json_str)
            return questions[:num_questions]
        except Exception as e:
            print(f"MCQ generation failed: {e}")
            # Fallback mock
            return [
                {
                    "question": f"What is 2 + 2 in {subject}?",
                    "options": ["A) 3", "B) 4", "C) 5", "D) 6"],
                    "correct_answer": "B) 4",
                    "feedback": "Basic arithmetic: 2 + 2 = 4."
                }
            ][:num_questions]

    # --------------------------------------------------------------------------
    # ENHANCED: GRADE MCQ
    # --------------------------------------------------------------------------
    def grade_mcq(self, questions: List[Dict], user_answers: Dict[int, str]) -> Dict:
        """
        Grade user answers.
        Returns: correct count, total, percentage, detailed results
        """
        correct = 0
        results = []

        for i, q in enumerate(questions):
            user_ans = user_answers.get(i, "")
            correct_ans = q["correct_answer"]
            is_correct = user_ans == correct_ans
            if is_correct:
                correct += 1
            results.append({
                "question": q["question"],
                "user_answer": user_ans,
                "correct_answer": correct_ans,
                "is_correct": is_correct,
                "feedback": q.get("feedback", "No feedback.")
            })

        percentage = (correct / len(questions)) * 100 if questions else 0

        return {
            "correct": correct,
            "total": len(questions),
            "percentage": round(percentage, 1),
            "results": results
        }

    # --------------------------------------------------------------------------
    # EXAM / GRADING / SUMMARY (Optional – keep or remove)
    # --------------------------------------------------------------------------
    def generate_exam_questions(self, subject, exam_type, num_questions):
        return self.generate_mcq_questions(subject, num_questions)

    def grade_short_answer(self, question, model_answer, user_answer):
        is_correct = len(user_answer) > 15
        feedback = "Correct!" if is_correct else "Add more detail."
        return {"is_correct": is_correct, "feedback": feedback}

    def summarize_text_hf(self, text: str) -> str:
        return "Summary not available (HF disabled)."
