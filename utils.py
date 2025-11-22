# utils.py — FULLY WORKING (2025)
import PyPDF2
import io
from typing import Optional
import streamlit as st
from deep_translator import GoogleTranslator
import nltk
import pathlib

_nltk_data = pathlib.Path(__file__).parent / "nltk_data"
if _nltk_data.exists():
    nltk.data.path.append(str(_nltk_data))

for resource in ['punkt', 'punkt_tab', 'averaged_perceptron_tagger']:
    try:
        nltk.data.find(f'tokenizers/{resource}')
    except LookupError:
        try:
            nltk.download(resource, quiet=True, download_dir=str(_nltk_data))
        except:
            pass

@st.cache_data(ttl=3600)
def cached_pdf_extract(pdf_bytes: bytes, filename: str) -> str:
    try:
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip() or "No text found in PDF."
    except Exception as e:
        st.error(f"PDF Error: {e}")
        return "Error reading PDF."

class Translator_Utils:
    def translate_text(self, text: str, target_lang: str = 'en') -> str:
        if not text.strip() or target_lang == 'en':
            return text
        try:
            return GoogleTranslator(source='auto', target=target_lang).translate(text)
        except:
            return text
