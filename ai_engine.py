# ai_engine.py
import streamlit as st
from openai import OpenAI
import json

class AIEngine:
    def __init__(self):
        # Initialize the OpenAI client. It automatically looks for 'OPENAI_API_KEY'
        # in the environment variables or in st.secrets if deployed on Streamlit Cloud.
        # Ensure your key is named 'OPENAI_API_KEY' in your secrets.toml file/Streamlit secrets.
        try:
            self.client = OpenAI(api_key=st.secrets['OPENAI_API_KEY'])
            self.model = "gpt-4o"  # Using a powerful model for complex tasks
        except Exception as e:
            st.error(f"Failed to initialize OpenAI Client. Check your OPENAI_API_KEY secret. Error: {e}")
            self.client = None

    def _call_openai(self, system_prompt, user_prompt, temperature=0.7):
        """Internal method to handle the API call."""
        if not self.client:
            return "AI service is currently unavailable. Please check the OpenAI API Key configuration."

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"An error occurred while calling the OpenAI API: {e}"

    def generate_response(self, user_prompt, system_prompt, temperature=0.7):
        """Generates a standard text response (Chat Tutor/PDF Q&A)."""
        return self._call_openai(system_prompt, user_prompt, temperature)

    def generate_exam_questions(self, subject, exam_type, count, topic):
        """Generates MCQ exam questions using JSON output."""
        system_prompt = f"""
        You are an expert Kenyan curriculum exam generator. Generate exactly {count} multiple-choice questions for the '{subject}' subject, suitable for a '{exam_type}' exam, focusing on the topic '{topic}'. 
        Each question must have 4 options (A, B, C, D) and specify the correct answer. 
        Respond ONLY with a JSON list of objects, strictly adhering to the following structure: 
        [
            {{"question": "...", "options": ["A: ...", "B: ...", "C: ...", "D: ..."], "answer": "The correct option text"}},
            ...
        ]
        """
        user_prompt = f"Generate {count} unique, high-difficulty questions on {subject} - {topic} for the {exam_type} level."
        
        # Use a low temperature for predictable output (JSON)
        json_response = self._call_openai(system_prompt, user_prompt, temperature=0.1)
        
        # Attempt to parse the JSON response
        try:
            return json.loads(json_response)
        except json.JSONDecodeError:
            st.error("Failed to parse AI-generated JSON. Please try again.")
            return []

    def grade_mcq(self, questions, user_answers):
        """Grades the user's answers against the correct answers provided in the questions list."""
        correct_count = 0
        total_questions = len(questions)
        feedback = []

        for i, q in enumerate(questions):
            correct_answer = q['answer']
            user_answer = user_answers.get(i)
            
            is_correct = user_answer == correct_answer
            
            if is_correct:
                correct_count += 1
            
            feedback.append({
                "question": q['question'],
                "user_answer": user_answer,
                "correct_answer": correct_answer,
                "is_correct": is_correct
            })
            
        percentage = (correct_count / total_questions) * 100 if total_questions > 0 else 0
        
        return {
            "score": correct_count,
            "total": total_questions,
            "percentage": round(percentage, 2),
            "feedback": feedback
        }

    def grade_essay(self, essay_text, rubric):
        """Grades an essay and provides feedback using JSON output."""
        system_prompt = f"""
        You are an expert Kenyan KCSE marker. Grade the following essay based on the '{rubric}' standard rubric. 
        Your grading MUST be objective, covering content, language, organization, and mechanics.
        Respond ONLY with a JSON object, strictly adhering to the following structure:
        {{"score": 15, "max_score": 20, "feedback": "Detailed feedback on Content, Language, etc.", "suggestions": "Specific areas for improvement"}}
        The score must be between 0 and 20.
        """
        user_prompt = f"Grade this essay:\n\n{essay_text}"
        
        json_response = self._call_openai(system_prompt, user_prompt, temperature=0.2)
        
        try:
            return json.loads(json_response)
        except json.JSONDecodeError:
            return {"score": 0, "max_score": 20, "feedback": "AI grading failed due to format error.", "suggestions": "Ensure the essay is clear."}
