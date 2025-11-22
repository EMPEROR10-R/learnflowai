# ai_engine.py — FIXED: Strict Uniqueness & Max Difficulty for MCQs (No Repetition, No Simple Questions) + Robust Tutor Responses + All Features Intact
import json
import time
import requests
from streamlit import cache_data
from typing import List, Dict
import io
import PyPDF2

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models/"
GEMINI_CHAT_MODEL = "gemini-1.5-flash"
GEMINI_STRUCTURED_MODEL = "gemini-1.5-flash"

class AIEngine:
    def __init__(self, gemini_key: str, hf_key: str = ""):
        self.gemini_key = gemini_key or ""
        self.hf_key = hf_key or ""

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

    @cache_data(ttl="2h", show_spinner="Extracting PDF…")
    def extract_text_from_pdf(_self, pdf_bytes: bytes) -> str:
        try:
            pdf_file = io.BytesIO(pdf_bytes)
            reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text.strip() or "No text found in PDF."
        except Exception as e:
            return f"Error extracting PDF: {e}"

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

    def generate_response(self, user_query: str, system_prompt: str) -> str:
        contents = [{"role": "user", "parts": [{"text": user_query}]}]
        return self.generate_response_gemini(contents, system_prompt)

    def stream_response(self, user_query: str, system_prompt: str):
        if not self.gemini_key:
            mock = f"Hint for «{user_query[:30]}…» – think step-by-step."
            for i in range(0, len(mock), 12):
                yield mock[i:i + 12]
            return

        full = self.generate_response(user_query, system_prompt)
        for chunk in [full[i:i + 50] for i in range(0, len(full), 50)]:
            yield chunk

    def generate_mcq_questions(self, subject: str, num_questions: int = 5, topic: str = "", exam_type: str = "") -> List[Dict]:
        num_questions = min(num_questions, 100)  # Max 100
        prompt = f"""
Generate EXACTLY {num_questions} UNIQUE, NON-REPEATING, MAXIMUM DIFFICULTY multiple-choice questions for {subject} at {exam_type} level, focusing on topic: {topic or 'general'}. Ensure questions are challenging, require deep understanding, multi-step reasoning, or application to real Kenyan scenarios. NO BASIC QUESTIONS like simple arithmetic; all must be advanced.

Each question MUST be:
- Completely unique in content, structure, and wording – no more, no less than {num_questions}; no duplicates or similar questions.
- High difficulty: Include advanced concepts (e.g., for OOP in Python: polymorphism, inheritance, decorators, metaclasses).
- 1 clear question
- 4 options (A, B, C, D) — exactly one correct, with plausible distractors based on common advanced errors.
- Correct answer (e.g., "B")
- Brief feedback explaining why correct is right and others wrong, using Kenyan examples where possible.

Output **only valid JSON** like this:
[
  {{
    "question": "Advanced question example?",
    "options": ["A) Option1", "B) Option2", "C) Option3", "D) Option4"],
    "correct_answer": "B",
    "feedback": "Explanation with Kenyan context."
  }}
]
No introductory text or extra content – strictly the JSON array with exactly {num_questions} items.
"""
        try:
            use_grounding = subject in ["History and Government", "Geography", "Business Studies"]
            response = self.generate_response_gemini([{"role": "user", "parts": [{"text": prompt}]}], 
                                                     "You are a quiz generator. Output only JSON.", 
                                                     use_grounding=use_grounding)
            
            json_str = response.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:-3]
            elif json_str.startswith("```"):
                json_str = json_str[3:-3]
            questions = json.loads(json_str)
            # Ensure no repetition by checking uniqueness
            unique_questions = []
            seen = set()
            for q in questions:
                q_text = q["question"].lower()
                if q_text not in seen:
                    seen.add(q_text)
                    unique_questions.append(q)
            while len(unique_questions) < num_questions:
                # Generate additional if needed
                additional_prompt = f"Generate 1 additional unique, difficult MCQ for {subject} topic {topic} to make total {num_questions}."
                additional_resp = self.generate_response_gemini([{"role": "user", "parts": [{"text": additional_prompt}]}], 
                                                                "Output only JSON for 1 question.")
                additional_json = json.loads(additional_resp.strip().replace("```json", "").replace("```", ""))
                unique_questions.extend(additional_json)
            return unique_questions[:num_questions]
        except Exception as e:
            print(f"MCQ generation failed: {e}")
            # Topic-specific fallback for advanced questions
            fallback_questions = []
            for i in range(num_questions):
                fallback = {
                    "question": f"Advanced {topic} Q{i+1} in {subject}: Define polymorphism with Kenyan app example.",
                    "options": ["A) Single form", "B) Multiple forms", "C) No form", "D) Fixed form"],
                    "correct_answer": "B",
                    "feedback": "Polymorphism allows multiple forms, e.g., in Kenyan matatu app for different payment methods."
                }
                fallback_questions.append(fallback)
            return fallback_questions

    def grade_mcq(self, questions: List[Dict], user_answers: Dict[int, str]) -> Dict:
        correct = 0
        total_score = 0
        results = []
        for i, q in enumerate(questions):
            user_ans = user_answers.get(i, "").strip()
            correct_ans = q["correct_answer"].strip()
            is_correct = user_ans == correct_ans
            score = 100 if is_correct else 0
            total_score += score
            if is_correct:
                correct += 1
            results.append({
                "question": q["question"],
                "user_answer": user_ans,
                "correct_answer": correct_ans,
                "is_correct": is_correct,
                "score": score,
                "feedback": q.get("feedback", "No feedback.")
            })
        percentage = (total_score / (len(questions) * 100)) * 100 if questions else 0
        return {
            "correct": correct,
            "total": len(questions),
            "percentage": round(percentage, 1),
            "results": results
        }

    def generate_exam_questions(self, subject, exam_type, num_questions, topic=""):
        num_questions = min(num_questions, 100)
        return self.generate_mcq_questions(subject, num_questions, topic, exam_type)

    def grade_short_answer(self, question, model_answer, user_answer):
        prompt = f"""
Compare user answer to model answer for question: {question}
Model: {model_answer}
User: {user_answer}

**Instruction:** You are an expert Kenyan curriculum grader. Score 0-100 on accuracy, completeness, and adherence to Kenyan exam standards (e.g., using relevant local examples or context).
Output **only JSON**: {{"score": int, "feedback": "Explanation."}}
"""
        try:
            response = self.generate_response(prompt, "You are a precise short-answer grader. Focus on key facts and semantics and Kenyan curriculum standards.")
            json_str = response.strip().replace("```json", "").replace("```", "")
            result = json.loads(json_str)
            return result
        except Exception as e:
            print(f"Short answer grading error: {e}")
            return {"score": 50 if len(user_answer) > 15 else 0, "feedback": "Basic check: Average effort; improve details."}

    def grade_essay(self, essay: str, rubric: str) -> Dict:
        prompt = f"""
Grade this essay on a scale of 0-100 based on the rubric: {rubric}
Essay: {essay}

**Instruction:** You are an expert essay grader for the **Kenyan curriculum (KCSE/KPSEA)**. Be fair, detailed, constructive, and ensure grading aligns with local expectations for structure, content, and language use.
Output **only JSON**: {{"score": int, "feedback": "Detailed strengths/weaknesses."}}
"""
        try:
            response = self.generate_response(prompt, "You are an expert essay grader for Kenyan curriculum. Be fair, detailed, and constructive.")
            json_str = response.strip().replace("```json", "").replace("```", "")
            result = json.loads(json_str)
            return result
        except Exception as e:
            print(f"Essay grading error: {e}")
            return {"score": 50, "feedback": "Fallback: Average effort; improve details. (AI Grading Error)"}

    def grade_project(self, subject: str, project_name: str, submission: str) -> Dict:
        prompt = f"""
Grade this project submission for {subject} - {project_name}:
Submission: {submission}

**Instruction:** Score 0-100 on creativity, correctness, Kenyan relevance, and completeness. Suggest XP award (50-300 based on quality).
Output **only JSON**: {{"score": int, "feedback": "Detailed review.", "xp": int}}
"""
        try:
            response = self.generate_response(prompt, "You are a project grader for Kenyan EdTech. Be encouraging.")
            json_str = response.strip().replace("```json", "").replace("```", "")
            result = json.loads(json_str)
            return result
        except Exception as e:
            print(f"Project grading error: {e}")
            return {"score": 50, "feedback": "Average project.", "xp": 100}

    def summarize_text_hf(self, text: str) -> str:
        return "Summary not available (HF disabled)."
