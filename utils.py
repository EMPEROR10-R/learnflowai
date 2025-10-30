import PyPDF2
import io
from typing import Optional, List
import streamlit as st
from googletrans import Translator
import nltk
import re

try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    try:
        nltk.download('punkt', quiet=True)
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
            'en': 'English',
            'es': 'Spanish',
            'fr': 'French',
            'de': 'German',
            'zh-cn': 'Chinese (Simplified)',
            'ja': 'Japanese',
            'ko': 'Korean',
            'ar': 'Arabic',
            'hi': 'Hindi',
            'pt': 'Portuguese',
            'ru': 'Russian',
            'it': 'Italian',
            'nl': 'Dutch',
            'pl': 'Polish',
            'tr': 'Turkish',
            'vi': 'Vietnamese',
            'th': 'Thai',
            'sv': 'Swedish',
            'da': 'Danish',
            'fi': 'Finnish'
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

class EssayGrader:
    @staticmethod
    def grade_essay(essay_text: str, rubric: dict = None) -> dict:
        if rubric is None:
            rubric = {
                'grammar': 30,
                'structure': 25,
                'content': 25,
                'vocabulary': 20
            }
        
        scores = {}
        feedback = []
        
        sentences = nltk.sent_tokenize(essay_text)
        words = nltk.word_tokenize(essay_text)
        
        word_count = len(words)
        sentence_count = len(sentences)
        avg_sentence_length = word_count / sentence_count if sentence_count > 0 else 0
        
        grammar_score = min(100, max(0, 100 - (abs(avg_sentence_length - 15) * 2)))
        scores['grammar'] = round(grammar_score * rubric['grammar'] / 100, 1)
        
        if sentence_count < 3:
            feedback.append("Try to develop your ideas with more sentences.")
        
        paragraphs = essay_text.split('\n\n')
        paragraph_count = len([p for p in paragraphs if p.strip()])
        
        if paragraph_count >= 3:
            structure_score = 90
        elif paragraph_count == 2:
            structure_score = 70
        else:
            structure_score = 50
        
        scores['structure'] = round(structure_score * rubric['structure'] / 100, 1)
        
        if paragraph_count < 3:
            feedback.append("Consider organizing your essay into introduction, body, and conclusion paragraphs.")
        
        if word_count < 100:
            content_score = 60
            feedback.append("Your essay is quite short. Try to expand on your ideas.")
        elif word_count < 200:
            content_score = 75
        elif word_count < 300:
            content_score = 85
        else:
            content_score = 95
        
        scores['content'] = round(content_score * rubric['content'] / 100, 1)
        
        unique_words = len(set(word.lower() for word in words if word.isalnum()))
        vocabulary_diversity = unique_words / word_count if word_count > 0 else 0
        
        vocabulary_score = min(100, vocabulary_diversity * 150)
        scores['vocabulary'] = round(vocabulary_score * rubric['vocabulary'] / 100, 1)
        
        if vocabulary_diversity < 0.5:
            feedback.append("Try to use a more diverse vocabulary.")
        
        total_score = sum(scores.values())
        
        if total_score >= 90:
            overall_feedback = "Excellent work!"
        elif total_score >= 80:
            overall_feedback = "Very good essay!"
        elif total_score >= 70:
            overall_feedback = "Good effort, with room for improvement."
        elif total_score >= 60:
            overall_feedback = "Fair work. Focus on the feedback to improve."
        else:
            overall_feedback = "Keep practicing! Review the feedback carefully."
        
        return {
            'total_score': round(total_score, 1),
            'breakdown': scores,
            'feedback': feedback,
            'overall': overall_feedback,
            'stats': {
                'word_count': word_count,
                'sentence_count': sentence_count,
                'paragraph_count': paragraph_count,
                'avg_sentence_length': round(avg_sentence_length, 1)
            }
        }

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
