import re
import json
from typing import List, Tuple

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

_DIARIZATION_PROMPT = (
    "You are a speaker diarization assistant. Analyze meeting transcripts and identify different speakers.\n"
    "CRITICAL: Return ONLY valid JSON. No markdown, no text before/after. Just pure JSON.\n\n"
    
    "REQUIRED JSON FORMAT:\n"
    "[\n"
    '  {"speaker": "Speaker Name or Identifier", "text": "What they said"},'
    '  {"speaker": "Another Speaker", "text": "Their statement"},'
    '  ...\n'
    "]\n\n"
    
    "DIARIZATION RULES:\n"
    "1. Identify distinct speakers based on:\n"
    "   • Explicit speaker labels (Speaker 1, Person A, etc.)\n"
    "   • Names mentioned (John, Ms. Smith, Anh Minh, etc.)\n"
    "   • Context clues (pronouns, speaking style, topics)\n"
    "   • Department/role mentions (HR, IT, Manager, etc.)\n\n"
    
    "2. Speaker Names:\n"
    "   • Use actual names if mentioned (e.g., 'John', 'Minh', 'Nguyen')\n"
    "   • Use titles if available (e.g., 'Mr. Smith', 'Anh Huy')\n"
    "   • Use roles if clear (e.g., 'Manager', 'IT Team')\n"
    "   • Use 'Speaker 1', 'Speaker 2', etc. only if no other identifier available\n\n"
    
    "3. Text Segments:\n"
    "   • Group consecutive statements by the same speaker\n"
    "   • Split when speaker changes\n"
    "   • Preserve original text, don't summarize\n\n"
    
    "4. If only one speaker detected, return single entry with their name or 'Meeting Transcript'\n\n"
    
    "CRITICAL: Return valid JSON array only. No markdown code blocks.\n"
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
                    {"role": "system", "content": "You are a speaker diarization assistant. Return ONLY valid JSON array."},
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
        "You are a speaker diarization assistant. Analyze meeting transcripts and identify different speakers.\n"
        "CRITICAL: Return ONLY valid JSON array. No markdown, no text before/after. Just pure JSON.\n\n"
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

# ------------------ PATTERN-BASED DIARIZATION (FALLBACK) ------------------
def _diarize_with_patterns(text: str) -> List[Tuple[str, str]]:
    """Fallback pattern-based speaker diarization"""
    if not text:
        return []
    
    text = re.sub(r'\.([A-Z])', r'. \1', text)
    
    speaker_patterns = [
        r'(?:Speaker\s*\d+)',
        r'(?:Người\s+nói\s*\d+)',
        r'(?:Person\s*\d+)',
        r'(?:P\d+)',
        r'(?:S\d+)',
        r'(?:Mr\.?\s+[A-Z][a-z]+)',
        r'(?:Ms\.?\s+[A-Z][a-z]+)',
        r'(?:Mrs\.?\s+[A-Z][a-z]+)',
        r'(?:Dr\.?\s+[A-Z][a-z]+)',
        r'(?:Anh\s+[A-Z][a-z]+)',
        r'(?:Chị\s+[A-Z][a-z]+)',
        r'(?:Ông\s+[A-Z][a-z]+)',
        r'(?:Bà\s+[A-Z][a-z]+)',
        r'(?:HR)',
        r'(?:Finance)',
        r'(?:IT)',
        r'(?:Manager[s]?)',
        r'(?:Team Lead)',
        r'(?:Director)',
    ]
    
    segments = []
    current_speaker = "Unknown"
    current_text = ""
    
    lines = text.split('\n')
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        speaker_found = None
        for pattern in speaker_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                speaker_found = match.group(0)
                break
        
        if speaker_found:
            if current_text.strip():
                segments.append((current_speaker, current_text.strip()))
            
            current_speaker = speaker_found
            current_text = re.sub(rf'^{re.escape(speaker_found)}:\s*', '', line)
            current_text = re.sub(rf'^{re.escape(speaker_found)}\s*', '', current_text)
        else:
            if current_text:
                current_text += " " + line
            else:
                current_text = line
    
    if current_text.strip():
        segments.append((current_speaker, current_text.strip()))
    
    if not segments or len(segments) == 1:
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        smart_segments = []
        current_speaker = None
        current_text = ""
        
        speaker_change_patterns = [
            (r'^(HR|Finance|IT|Engineering|Marketing|Sales|Legal|Management)\s+(?:will|needs?|must|should|to|is)', lambda m: m.group(1)),
            (r'^([A-Z][a-z]+)\s+(?:will|needs?|must|should|to)\s+', lambda m: m.group(1)),
            (r'\b(HR|Finance|IT|Engineering|Marketing|Sales|Legal|Management)\s+(?:will|needs?|must|should|to|is)', lambda m: m.group(1)),
            (r'\b([A-Z][a-z]+)\s+(?:will|to|must|should)\s+(?:draft|finalize|prepare|coordinate|review|implement|deploy|complete|launch)', lambda m: m.group(1)),
        ]
        
        for sentence in sentences:
            if not sentence:
                continue
            
            detected_speaker = None
            for pattern, extractor in speaker_change_patterns:
                match = re.search(pattern, sentence)
                if match:
                    detected_speaker = extractor(match)
                    if detected_speaker and detected_speaker.lower() not in ['decided', 'agreed', 'needs', 'must', 'should', 'will']:
                        break
                    detected_speaker = None
            
            if detected_speaker and detected_speaker != current_speaker:
                if current_text.strip():
                    smart_segments.append((current_speaker or "Unknown", current_text.strip()))
                current_speaker = detected_speaker
                current_text = sentence
            else:
                if current_text:
                    current_text += ". " + sentence
                else:
                    current_text = sentence
        
        if current_text.strip():
            smart_segments.append((current_speaker or "Unknown", current_text.strip()))
        
        if len([s for s in smart_segments if s[0] != "Unknown"]) > 1:
            smart_segments = [s for s in smart_segments if s[0] != "Unknown"]
        
        if len(smart_segments) > 1:
            return smart_segments
        
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        if len(sentences) > 5:
            chunk_segments = []
            chunk_size = max(3, len(sentences) // 5)
            for i in range(0, len(sentences), chunk_size):
                chunk = '. '.join(sentences[i:i+chunk_size])
                speaker_num = (i // chunk_size) + 1
                chunk_segments.append((f"Speaker {speaker_num}", chunk))
            return chunk_segments
        
        return [("Meeting Transcript", text)]
    
    return segments

# ------------------ MAIN DIARIZE FUNCTION ------------------
def diarize(text: str) -> List[Tuple[str, str]]:
    """
    Speaker diarization using LLM (OpenAI with Gemini fallback), 
    falls back to pattern-based if LLM fails.
    """
    if not text:
        return []
    
    # Try LLM-based diarization first
    try:
        prompt = (
            _DIARIZATION_PROMPT
            + "\n\nMeeting Transcript:\n"
            + text
            + "\n\nRespond with ONLY valid JSON array, no other text:"
        )
        
        response_text = _generate_with_llm(prompt, max_tokens=2048)
        
        if response_text:
            try:
                # Clean the response text
                cleaned_text = response_text.strip()
                if cleaned_text.startswith("```json"):
                    cleaned_text = cleaned_text[7:]
                if cleaned_text.startswith("```"):
                    cleaned_text = cleaned_text[3:]
                if cleaned_text.endswith("```"):
                    cleaned_text = cleaned_text[:-3]
                
                cleaned_text = cleaned_text.strip()
                
                # Try to extract JSON array from text if embedded
                json_match = re.search(r'\[.*\]', cleaned_text, re.DOTALL)
                if json_match:
                    cleaned_text = json_match.group(0)
                
                # Parse JSON
                diarization_data = json.loads(cleaned_text)
                
                # Convert to List[Tuple[str, str]] format
                if isinstance(diarization_data, list):
                    segments = []
                    for item in diarization_data:
                        if isinstance(item, dict):
                            speaker = item.get("speaker", "Unknown")
                            text_content = item.get("text", "")
                            if text_content:
                                segments.append((speaker, text_content))
                    
                    if segments:
                        return segments
            except (json.JSONDecodeError, Exception):
                pass
    except Exception:
        pass
    
    return _diarize_with_patterns(text)
