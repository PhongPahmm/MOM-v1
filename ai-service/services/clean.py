import re
import json
from typing import List

try:
    from openai import OpenAI
    from openai import AuthenticationError, PermissionDeniedError, APIError
except ImportError:
    OpenAI = None
    AuthenticationError = None
    PermissionDeniedError = None
    APIError = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from core.config import settings

# Global client cache
_openai_client = None
_gemini_client = None

_CLEAN_PROMPT = (
    "You are a transcript cleaning assistant. Clean and normalize meeting transcript text.\n"
    "CRITICAL: Return ONLY the cleaned text. No markdown, no JSON, no explanations. Just the cleaned text.\n\n"
    
    "CLEANING RULES:\n"
    "1. Remove ONLY true filler words that don't carry meaning:\n"
    "   • English: 'uh', 'um', 'ah', 'er', 'hmm', 'you know', 'i mean', 'kind of', 'sort of'\n"
    "   • Vietnamese: 'ừ', 'ờ', 'à', 'ạ', 'nhé', 'nhá'\n"
    "   • Be conservative - when in doubt, keep the word\n\n"
    
    "2. Normalize whitespace:\n"
    "   • Remove multiple spaces\n"
    "   • Fix spacing around punctuation\n"
    "   • Ensure single space between words\n\n"
    
    "3. Fix punctuation:\n"
    "   • Ensure proper spacing around punctuation marks\n"
    "   • Capitalize first letter of sentences\n"
    "   • Ensure sentences end with proper punctuation\n\n"
    
    "4. Preserve all meaningful content:\n"
    "   • Keep all names, dates, numbers, technical terms\n"
    "   • Don't summarize or paraphrase\n"
    "   • Maintain original meaning and structure\n\n"
    
    "CRITICAL: Return ONLY the cleaned text, nothing else.\n"
)

# ------------------ OPENAI CLIENT INIT ------------------
def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        if OpenAI is None:
            raise ImportError("Install OpenAI with: pip install openai")
        api_key = settings.openai_api_key
        if not api_key:
            import os
            api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("Missing OPENAI_API_KEY in .env or environment.")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client

# ------------------ CONFIGURE GEMINI API KEY ------------------
def _configure_gemini_api_key():
    """Ensure Gemini API key is configured"""
    import os
    api_key = None
    
    api_key = settings.google_api_key
    
    if not api_key:
        api_key = os.getenv("GOOGLE_API_KEY")
    
    if not api_key:
        for key, value in os.environ.items():
            if key.upper() == "GOOGLE_API_KEY":
                api_key = value
                break
    
    if not api_key:
        raise ValueError(
            "Missing GOOGLE_API_KEY. Please set it in:\n"
            "1. .env file: GOOGLE_API_KEY=your_key\n"
            "2. Environment variable: export GOOGLE_API_KEY=your_key (Linux/Mac) or set GOOGLE_API_KEY=your_key (Windows)"
        )
    
    genai.configure(api_key=api_key)
    return api_key

# ------------------ GEMINI CLIENT INIT ------------------
def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        if genai is None:
            raise ImportError("Install Google Generative AI with: pip install google-generativeai")
        _configure_gemini_api_key()
        
        model_names = [
            'gemini-1.5-flash-latest',
            'gemini-1.5-flash',
            'gemini-pro',
        ]
        
        _gemini_client = None
        last_error = None
        
        for model_name in model_names:
            try:
                _gemini_client = genai.GenerativeModel(model_name)
                break
            except Exception as e:
                last_error = e
                continue
        
        if _gemini_client is None:
            try:
                for model in genai.list_models():
                    if 'generateContent' in model.supported_generation_methods:
                        model_name = model.name.replace('models/', '')
                        try:
                            _gemini_client = genai.GenerativeModel(model_name)
                            break
                        except:
                            continue
            except:
                pass
            
            if _gemini_client is None:
                raise RuntimeError(
                    f"Failed to initialize Gemini client. "
                    f"Last error: {last_error}. "
                    f"Please check your GOOGLE_API_KEY."
                )
    return _gemini_client

# ------------------ LLM GENERATION WITH FALLBACK ------------------
def _generate_with_llm(prompt: str, max_tokens: int = 2048) -> str:
    """Generate text with OpenAI API, fallback to Gemini if API key expired/invalid"""
    if OpenAI is not None and settings.openai_api_key:
        try:
            client = _get_openai_client()
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a transcript cleaning assistant. Return ONLY the cleaned text, nothing else."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=max_tokens,
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            error_str = str(e).lower()
            
            is_auth_error = (
                (AuthenticationError is not None and isinstance(e, AuthenticationError)) or
                (PermissionDeniedError is not None and isinstance(e, PermissionDeniedError)) or
                any(keyword in error_str for keyword in ["api key", "authentication", "invalid", "expired", "unauthorized", "permission denied", "insufficient_quota", "quota"]) or
                "401" in error_str or
                "403" in error_str or
                "429" in error_str
            )
            
            if is_auth_error:
                return _generate_with_gemini(prompt, max_tokens)
            elif isinstance(e, ValueError) and "Missing OPENAI_API_KEY" in str(e):
                return _generate_with_gemini(prompt, max_tokens)
            elif APIError is not None and isinstance(e, APIError):
                try:
                    return _generate_with_gemini(prompt, max_tokens)
                except Exception as gemini_error:
                    raise RuntimeError(f"Both OpenAI API and Gemini failed. Please check your setup.")
            else:
                raise
    
    try:
        return _generate_with_gemini(prompt, max_tokens)
    except Exception as e:
        raise RuntimeError(f"Gemini API failed: {e}")

# ------------------ GEMINI GENERATION ------------------
def _generate_with_gemini(prompt: str, max_tokens: int = 2048) -> str:
    """Generate text using Google Gemini API with fallback to different models"""
    global _gemini_client
    
    try:
        _configure_gemini_api_key()
    except ValueError as key_error:
        raise RuntimeError(f"Gemini API key not configured: {key_error}")
    
    model_names = [
        'gemini-1.5-flash-latest',
        'gemini-1.5-flash',
        'gemini-pro',
        'gemini-1.0-pro',
    ]
    
    try:
        for model in genai.list_models():
            if 'generateContent' in model.supported_generation_methods:
                model_name = model.name.replace('models/', '')
                if model_name not in model_names:
                    model_names.append(model_name)
    except:
        pass
    
    full_prompt = (
        "You are a transcript cleaning assistant. Clean and normalize meeting transcript text.\n"
        "CRITICAL: Return ONLY the cleaned text. No markdown, no JSON, no explanations. Just the cleaned text.\n\n"
        + prompt
    )
    
    last_error = None
    
    if _gemini_client is not None:
        try:
            response = _gemini_client.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=max_tokens,
                )
            )
            return response.text.strip()
        except Exception as e:
            error_str = str(e).lower()
            if "404" in error_str or "not found" in error_str:
                _gemini_client = None
            else:
                if "api key" in error_str or "authentication" in error_str or "403" in error_str or "401" in error_str:
                    raise ValueError(f"Gemini API key error: {e}")
                raise RuntimeError(f"Gemini API error: {e}")
    
    for model_name in model_names:
        try:
            _configure_gemini_api_key()
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=max_tokens,
                )
            )
            _gemini_client = model
            return response.text.strip()
        except Exception as e:
            error_str = str(e).lower()
            if "404" in error_str or "not found" in error_str:
                last_error = e
                continue
            elif "api key" in error_str or "authentication" in error_str:
                raise ValueError(f"Gemini API key error: {e}")
            else:
                last_error = e
                continue
    
    raise RuntimeError(
        f"Gemini API error: All models failed. Last error: {last_error}. "
        f"Please check your GOOGLE_API_KEY."
    )

# ------------------ PATTERN-BASED CLEANING (FALLBACK) ------------------
def _clean_with_patterns(text: str) -> str:
    """Fallback pattern-based transcript cleaning"""
    if not text:
        return ""
    
    # ONLY remove true filler words that don't carry meaning
    filler_words = [
        "uh", "um", "ah", "eh", "er", "hmm", "oh",
        "you know", "i mean", "kind of", "sort of", "like actually",
        "ừ", "ờ", "à", "ạ", "nhé", "nhá"
    ]
    
    # Normalize whitespace first
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    # Remove ONLY obvious filler phrases (case insensitive, word boundary aware)
    for filler in filler_words:
        pattern = r'\b' + re.escape(filler) + r'\b'
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Clean up punctuation spacing (but preserve the punctuation itself)
    text = re.sub(r'\s*\.\s*', '. ', text)
    text = re.sub(r'\s*,\s*', ', ', text)
    text = re.sub(r'\s*;\s*', '; ', text)
    text = re.sub(r'\s*:\s*', ': ', text)
    text = re.sub(r'\s*\?\s*', '? ', text)
    text = re.sub(r'\s*!\s*', '! ', text)
    
    # Fix multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    # Remove spaces before punctuation at end of sentences
    text = re.sub(r'\s+([.!?])', r'\1', text)
    
    # Capitalize first letter of sentences
    sentences = re.split(r'([.!?])\s+', text)
    result = []
    for i, part in enumerate(sentences):
        if i % 2 == 0 and part:  # Text parts (not punctuation)
            result.append(part.strip().capitalize() if part.strip() else part)
        else:  # Punctuation
            result.append(part)
    text = ''.join(result)
    
    # Final cleanup
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    # Ensure sentence ends with punctuation
    if text and not text[-1] in '.!?':
        text += '.'
    
    return text

# ------------------ MAIN CLEAN FUNCTION ------------------
def clean_transcript(text: str) -> str:
    """
    Clean and normalize transcript text using LLM (OpenAI with Gemini fallback),
    falls back to pattern-based cleaning if LLM fails.
    """
    if not text:
        return ""
    
    # Try LLM-based cleaning first
    try:
        prompt = (
            _CLEAN_PROMPT
            + "\n\nOriginal Transcript:\n"
            + text
            + "\n\nCleaned Transcript (return ONLY the cleaned text, nothing else):"
        )
        
        cleaned_text = _generate_with_llm(prompt, max_tokens=2048)
        
        if cleaned_text:
            # Clean up response (remove markdown if present)
            cleaned_text = cleaned_text.strip()
            if cleaned_text.startswith("```"):
                # Remove markdown code blocks
                lines = cleaned_text.split('\n')
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                cleaned_text = '\n'.join(lines).strip()
            
            if len(cleaned_text) > 0 and len(cleaned_text) <= len(text) * 1.5:
                return cleaned_text
    except Exception:
        pass
    
    return _clean_with_patterns(text)
