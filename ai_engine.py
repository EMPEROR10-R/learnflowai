import os
from typing import Optional, Dict, Any
import streamlit as st

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

class AIEngine:
    def __init__(self, api_key: Optional[str] = None):
        self.groq_api_key = api_key
        self.client = None
        
        if self.groq_api_key and GROQ_AVAILABLE:
            try:
                self.client = Groq(api_key=self.groq_api_key)
                self.engine_type = "groq"
            except Exception as e:
                st.warning(f"Groq initialization failed: {str(e)}")
                self.engine_type = "fallback"
        else:
            self.engine_type = "fallback"
    
    def generate_response(
        self, 
        prompt: str, 
        system_prompt: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.7
    ) -> str:
        if self.engine_type == "groq" and self.client:
            try:
                return self._groq_generate(prompt, system_prompt, max_tokens, temperature)
            except Exception as e:
                st.error(f"Groq API Error: {str(e)}")
                return self._fallback_response(prompt)
        else:
            return self._fallback_response(prompt)
    
    def _groq_generate(
        self, 
        prompt: str, 
        system_prompt: str,
        max_tokens: int,
        temperature: float
    ) -> str:
        messages = []
        
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        messages.append({
            "role": "user",
            "content": prompt
        })
        
        try:
            chat_completion = self.client.chat.completions.create(
                messages=messages,
                model="llama3-8b-8192",
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=1,
                stream=False
            )
            
            return chat_completion.choices[0].message.content
        
        except Exception as e:
            raise Exception(f"Groq API call failed: {str(e)}")
    
    def _fallback_response(self, prompt: str) -> str:
        return """I'm currently running in demo mode without an AI API key.

To unlock full AI tutoring capabilities:
1. Get a FREE Groq API key from: https://console.groq.com
2. Enter it in the sidebar settings
3. Enjoy unlimited AI-powered learning!

**Demo Response:**
I'd love to help you with that question! Here's how I would approach it using the Socratic method:

1. What do you already know about this topic?
2. What have you tried so far?
3. What specific part is confusing you?

Once you add your Groq API key, I'll provide personalized, interactive tutoring that guides you to discover answers yourself!"""
    
    def stream_response(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.7
    ):
        if self.engine_type == "groq" and self.client:
            try:
                messages = []
                
                if system_prompt:
                    messages.append({
                        "role": "system",
                        "content": system_prompt
                    })
                
                messages.append({
                    "role": "user",
                    "content": prompt
                })
                
                stream = self.client.chat.completions.create(
                    messages=messages,
                    model="llama3-8b-8192",
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=1,
                    stream=True
                )
                
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
            
            except Exception as e:
                yield f"\n\nError: {str(e)}\n\nPlease check your Groq API key."
        else:
            yield self._fallback_response(prompt)
    
    def is_configured(self) -> bool:
        return self.engine_type == "groq" and self.client is not None
    
    def get_engine_name(self) -> str:
        if self.engine_type == "groq":
            return "Groq (Llama 3 8B)"
        return "Demo Mode"

@st.cache_data(ttl=3600)
def cached_ai_response(prompt: str, system_prompt: str, api_key: str) -> str:
    engine = AIEngine(api_key)
    return engine.generate_response(prompt, system_prompt)
