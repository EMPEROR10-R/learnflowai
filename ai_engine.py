# ai_engine.py — FINAL FIXED VERSION (PYTHON 3.13 SAFE)

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
            st.success("AI Engine Ready (gpt-4o-mini)")
        except Exception as e:
            st.error(f"OpenAI Error: {e}")
            self.client = None

    def _call_ai(self, system_prompt, user_prompt, temperature=0.7):
        if not self.client:
            return "AI is offline. Check your OpenAI key."

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
                max_tokens=4000
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"AI Error: {e}"

    def generate_response(
        self,
        user_prompt,
        system_prompt="You are a helpful Kenyan curriculum tutor.",
        temperature=0.7
    ):
        return self._call_ai(system_prompt, user_prompt, temperature)

    def generate_exam_questions(self, subject, exam_type, count, topic):
        system_prompt = f"""
You are an expert Kenyan exam creator for {exam_type}.
Generate EXACTLY {count} high-quality MCQs on {subject}.
Topic: {topic}

Output ONLY valid JSON array:
[
  {{
    "question": "What is 2+2?",
    "options": ["A: 1", "B: 2", "C: 3", "D: 4"],
    "answer": "D: 4"
  }}
]
No markdown. No extra text.
"""

        raw = self._call_ai(system_prompt, "Generate questions", temperature=0.1)

        try:
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.replace("```json", "").replace("```", "")
            return json.loads(raw)
        except Exception:
            st.error("Failed to parse questions. AI returned invalid JSON.")
            return []

    def grade_mcq(self, questions, user_answers):
        correct_count = 0
        feedback = []

        for i, q in enumerate(questions):
            user_ans = user_answers.get(i, "").strip()
            correct_ans = (
                q["answer"].split(":", 1)[1].strip()
                if ":" in q["answer"]
                else q["answer"]
            )

            is_correct = user_ans == correct_ans
            if is_correct:
                correct_count += 1

            feedback.append({
                "question": q["question"],
                "your_answer": user_ans,
                "correct_answer": correct_ans,
                "is_correct": is_correct
            })

        percentage = (correct_count / len(questions) * 100) if questions else 0

        return {
            "score": correct_count,
            "total": len(questions),
            "percentage": round(percentage, 1),
            "feedback": feedback
        }

    def grade_essay(self, essay_text, rubric="KCSE Standard"):
        system_prompt = """
You are a strict but fair KCSE English examiner.

Grade this essay out of 20 marks based on:
- Content (8)
- Expression (6)
- Organization (4)
- Mechanics (2)

Respond ONLY with valid JSON:
{
  "score": 15,
  "max_score": 20,
  "feedback": "Detailed breakdown",
  "suggestions": "How to improve"
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
                "suggestions": "Try again"
            }
