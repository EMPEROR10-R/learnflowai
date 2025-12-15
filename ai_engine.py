# ai_engine.py — PYTHON 3.13 SAFE | STREAMLIT CLOUD SAFE

import streamlit as st
from openai import OpenAI
import json
import os


class AIEngine:
    def __init__(self):
        api_key = os.environ.get("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY")

        if not api_key:
            st.error("OPENAI_API_KEY not found in Streamlit secrets!")
            self.client = None
            return

        try:
            self.client = OpenAI(api_key=api_key)
            self.model = "gpt-4o-mini"
        except Exception as e:
            st.error(f"OpenAI init error: {e}")
            self.client = None

    def _call_ai(self, system_prompt, user_prompt, temperature=0.7):
        if not self.client:
            return "AI unavailable"

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=4000,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"AI error: {e}"

    def generate_response(self, user_prompt):
        return self._call_ai(
            "You are a helpful Kenyan curriculum tutor.",
            user_prompt,
        )

    def generate_exam_questions(self, subject, exam_type, count, topic):
        system_prompt = f"""
Generate EXACTLY {count} Kenyan exam MCQs.

Subject: {subject}
Exam: {exam_type}
Topic: {topic}

Return ONLY valid JSON:
[
  {{
    "question": "...",
    "options": ["A: ...", "B: ...", "C: ...", "D: ..."],
    "answer": "A: ..."
  }}
]
"""

        raw = self._call_ai(system_prompt, "Generate now", temperature=0.1)

        try:
            raw = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(raw)
        except Exception:
            st.error("Invalid MCQ JSON returned")
            return []

    def grade_mcq(self, questions, user_answers):
        score = 0
        feedback = []

        for i, q in enumerate(questions):
            user_ans = user_answers.get(i, "")
            correct_ans = q["answer"].split(":", 1)[1].strip()
            is_correct = user_ans == correct_ans

            if is_correct:
                score += 1

            feedback.append({
                "question": q["question"],
                "your_answer": user_ans,
                "correct_answer": correct_ans,
                "is_correct": is_correct,
            })

        percentage = (score / len(questions) * 100) if questions else 0

        return {
            "score": score,
            "total": len(questions),
            "percentage": round(percentage, 1),
            "feedback": feedback,
        }

    def grade_essay(self, essay_text):
        system_prompt = """
Grade this KCSE essay out of 20.
Return ONLY JSON:
{
  "score": 14,
  "max_score": 20,
  "feedback": "...",
  "suggestions": "..."
}
"""
        raw = self._call_ai(system_prompt, essay_text, temperature=0.3)

        try:
            return json.loads(raw)
        except Exception:
            return {
                "score": 0,
                "max_score": 20,
                "feedback": "Grading failed",
                "suggestions": "Retry",
            }
