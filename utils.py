# utils.py — Updated with voice input fully enabled
import PyPDF2
import io
from typing import Optional, List
import streamlit as st
from googletrans import Translator
import nltk
import re
import pathlib

_nltk_data = pathlib.Path(__file__).parent / "nltk_data"
if _nltk_data.exists():
    nltk.data.path.append(str(_nltk_data))

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    try:
        nltk.download('punkt', quiet=True)
    except:
        pass

try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    try:
        nltk.download('punkt_tab', quiet=True)
    except:
        pass

try:
    nltk.data.find('averaged_perceptron_tagger')
except LookupError:
    try:
        nltk.download('averaged_perceptron_tagger', quiet=True)
    except:
        pass

class PDFParser:
    @staticmethod
    def extract_text(pdf_file) -> Optional[str]:
        try:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text.strip()
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
        self.translator = Translator()
        self.supported_languages = {
            'en': 'English', 'es': 'Spanish', 'fr': 'French', 'de': 'German',
            'zh-cn': 'Chinese (Simplified)', 'ja': 'Japanese', 'ko': 'Korean',
            'ar': 'Arabic', 'hi': 'Hindi', 'pt': 'Portuguese', 'ru': 'Russian',
            'it': 'Italian', 'nl': 'Dutch', 'pl': 'Polish', 'tr': 'Turkish',
            'vi': 'Vietnamese', 'th': 'Thai', 'sv': 'Swedish', 'da': 'Danish', 'fi': 'Finnish',
            'sw': 'Kiswahili'  # Added Kiswahili
        }
    
    def translate_text(self, text: str, target_lang: str = 'en', source_lang: str = 'auto') -> str:
        try:
            if target_lang == source_lang or target_lang == 'en':
                return text
            translation = self.translator.translate(text, src=source_lang, dest=target_lang)
            return translation.text
        except Exception as e:
            st.warning(f"Translation error: {str(e)}")
            return text
    
    def detect_language(self, text: str) -> str:
        try:
            detection = self.translator.detect(text)
            return detection.lang
        except:
            return 'en'

class VoiceInputHelper:
    @staticmethod
    def get_voice_input_html() -> str:
        return """
        <script>
        function startVoiceRecognition() {
            if ('webkitSpeechRecognition' in window) {
                const recognition = new webkitSpeechRecognition();
                recognition.continuous = false;
                recognition.interimResults = false;
                
                recognition.onresult = function(event) {
                    const transcript = event.results[0][0].transcript;
                    window.parent.postMessage({type: 'voice_input', text: transcript}, '*');
                };
                
                recognition.onerror = function(event) {
                    console.error('Speech recognition error:', event.error);
                };
                
                recognition.start();
            } else {
                alert('Voice recognition is not supported in your browser. Please use Chrome or Edge.');
            }
        }
        </script>
        """

@st.cache_data(ttl=3600)
def cached_translate(text: str, target_lang: str) -> str:
    translator = Translator_Utils()
    return translator.translate_text(text, target_lang)

@st.cache_data(ttl=3600)
def cached_pdf_extract(file_bytes: bytes, filename: str) -> str:
    pdf_file = io.BytesIO(file_bytes)
    return PDFParser.extract_text(pdf_file)
