# ai_engine.py — FIXED 2025: OpenAI Compatible + Error Handling + JSON Strict + Added Gemini Fallback (if key provided)
import streamlit as st
from openai import OpenAI
import json
import os

class AIEngine:
    def __init__(self):
        # Try OpenAI first
        try:
            self.client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY') or st.secrets.get('OPENAI_API_KEY'))
            self.model = "gpt-4o-mini"  # Efficient model
            self.provider = "openai"
        except:
            # Fallback to Gemini if available
            try:
                import google.generativeai as genai
                genai.configure(api_key=os.environ.get('GEMINI_API_KEY') or st.secrets.get('GEMINI_API_KEY'))
                self.client = genai.GenerativeModel('gemini-1.5-flash')
                self.model = "gemini-1.5-flash"
                self.provider = "gemini"
            except Exception as e:
                st.error(f"AI Init Error: {e}")
                self.client = None
                self.provider = None

    def _call_ai(self, system_prompt, user_prompt, temperature=0.7):
        if not self.client:
            return "AI unavailable. Check API keys."

        try:
            if self.provider == "openai":
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                    temperature=temperature
                )
                return response.choices[0].message.content
            elif self.provider == "gemini":
                prompt = f"{system_prompt}\n\n{user_prompt}"
                response = self.client.generate_content(prompt, generation_config={"temperature": temperature})
                return response.text
        except Exception as e:
            return f"AI Error: {e}"

    def generate_response(self, user_prompt, system_prompt="", temperature=0.7):
        return self._call_ai(system_prompt or "You are a helpful Kenyan curriculum AI tutor.", user_prompt, temperature)

    def generate_exam_questions(self, subject, exam_type, count, topic):
        system_prompt = f"""
        Expert Kenyan exam creator. Generate EXACTLY {count} MCQs for {subject} ({exam_type}) on '{topic}'.
        Kenyan curriculum. Each: 4 options A-D, one correct.
        Output ONLY JSON list: 
        [{{"question": "Q text", "options": ["A: opt1", "B: opt2", "C: opt3", "D: opt4"], "answer": "A: correct text"}}]
        No extra text.
        """
        user_prompt = f"Create {count} hard, unique questions."
        json_str = self._call_ai(system_prompt, user_prompt, temperature=0.1)
        try:
            return json.loads(json_str)
        except:
            return []

    def grade_mcq(self, questions, user_answers):
        correct = sum(user_answers.get(i, "") == q["answer"].split(":")[0].strip() for i, q in enumerate(questions))
        total = len(questions)
        percentage = (correct / total * 100) if total else 0
        return {"score": correct, "total": total, "percentage": round(percentage, 2), "feedback": []}  # Simplified feedback

    def grade_essay(self, essay_text, rubric="KCSE"):
        system_prompt = f"""
        Expert KCSE essay grader. Grade essay on {rubric} rubric (0-20).
        Objective: content, language, organization, mechanics.
        Output ONLY JSON: {{"score": 15, "max_score": 20, "feedback": "Detailed...", "suggestions": "Improve..."}}
        No extra text.
        """
        json_str = self._call_ai(system_prompt, essay_text, temperature=0.2)
        try:
            return json.loads(json_str)
        except:
            return {"score": 0, "max_score": 20, "feedback": "Error", "suggestions": ""}