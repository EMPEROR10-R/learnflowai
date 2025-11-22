# utils.py — FULLY FIXED: googletrans replaced with deep-translator (Python 3.13 + Streamlit Safe)
import PyPDF2
import io
from typing import Optional, List
import streamlit as st
from deep_translator import GoogleTranslator
import nltk
import re
import pathlib

_nltk_data = pathlib.Path(__file__).parent / "nltk_data"
if _nltk_data.exists():
    nltk.data.path.append(str(_nltk_data))

# Download NLTK data if missing
for resource in ['punkt', 'punkt_tab', 'averaged_perceptron_tagger']:
    try:
        nltk.data.find(f'tokenizers/{resource}')
    except LookupError:
        try:
            nltk.download(resource, quiet=True, download_dir=str(_nltk_data))
        except:
            pass

class PDFParser:
    @staticmethod
    def extract_text(pdf_file) -> Optional[str]:
        try:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            return text.strip() if text.strip() else "No text extracted from PDF."
        except Exception as e:
            st.error(f"Error reading PDF: {str(e)}")
            return None
    
    @staticmethod
    def summarize_content(text: str, max_length: int = 500) -> str:
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..."

class Translator_Utils:
    def __init__(self):
        self.supported_languages = {
            'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
            'zh-cn': 'Chinese (Simplified)', 'ja': 'Japanese', 'ko': 'Korean',
            'ar': 'Arabic', 'hi': 'Hindi', 'pt': 'Portuguese', 'ru': 'Russian',
            'it': 'Italian', 'nl': 'Dutch', 'pl': 'Polish', 'tr': 'Turkish',
            'vi': 'Vietnamese', 'th': 'Thai', 'sv': 'Swedish', 'da': 'Danish',
            'fi': 'Finnish', 'sw': 'Kiswahili'
        }
    
    def translate_text(self, text: str, target_lang: str = 'en', source_lang: str = 'auto') -> str:
        if not text.strip():
            return text
        if target_lang == 'en' or target_lang == source_lang:
            return text
        try:
            translated = GoogleTranslator(source=source_lang, target=target_lang).translate(text)
            return translated or text
        except Exception as e:
            st.warning(f"Translation failed: {str(e)}")
            return text
    
    def detect_language(self, text: str) -> str:
        if not text.strip():
            return 'en'
        try:
            return GoogleTranslator(source='auto', target='en').detect(text)
        except:
            return 'en'

class VoiceInputHelper:
    @staticmethod
    def get_voice_input_html() -> str:
        return """
        <script>
        function startVoiceRecognition() {
            if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
                const SpeechRecognition = window.webkitSpeechRecognition || window.SpeechRecognition;
                const recognition = new SpeechRecognition();
                recognition.continuous = false;
                recognition.interimResults = false;
                recognition.lang = 'en-US';  // You can make this dynamic

                recognition.onresult = function(event) {
                    const transcript = event.results[0][0].transcript;
                    window.parent.postMessage({type: 'voice_input', text: transcript}, '*');
                };
                
                recognition.onerror = function(event) {
                    console.error('Speech recognition error:', event.error);
                    alert('Voice input error: ' + event.error);
                };
                
                recognition.onend = function() {
                    console.log('Voice recognition ended.');
                };

                recognition.start();
            } else {
                alert('Sorry, your browser does not support voice input. Try Chrome/Edge.');
            }
        }
        </script>
        <button onclick="startVoiceRecognition()" style="padding: 10px; font-size: 16px;">
            Hold to Speak
        </button>
        """

@st.cache_data(ttl=3600)
def cached_translate(text: str, target_lang: str) -> str:
    translator = Translator_Utils()
    return translator.translate_text(text, target_lang)

@st.cache_data(ttl=3600)
def cached_pdf_extract(file_bytes: bytes, filename: str) -> str:
    pdf_file = io.BytesIO(file_bytes)
    return PDFParser.extract_text(pdf_file) or "No text found."
