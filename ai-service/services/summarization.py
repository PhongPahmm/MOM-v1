from typing import List, Dict, Any
import json
import re

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

_SYSTEM_PROMPT = (
    "You are a precise meeting minutes assistant. Extract structured information from meeting transcripts.\n"
    "CRITICAL: Return ONLY valid JSON. No markdown, no text before/after. Just pure JSON.\n\n"
    
    "REQUIRED JSON FORMAT:\n"
    "{\n"
    '  "title": "string - concise meeting title (max 80 chars)",\n'
    '  "date": "string - exact date if mentioned, or \'To be determined\'",\n'
    '  "time": "string - exact time if mentioned, or \'To be determined\'",\n'
    '  "attendants": ["array of names mentioned in meeting"],\n'
    '  "project_name": "string - project name if explicitly mentioned, or \'To be determined\'",\n'
    '  "customer": "string - customer/client name if mentioned, or \'To be determined\'",\n'
    '  "table_of_content": ["array of main topics discussed (5-10 items)"],\n'
    '  "main_content": "string - comprehensive summary (200-500 words)"\n'
    "}\n\n"
    
    "EXTRACTION RULES:\n"
    "1. TITLE: Create clear, descriptive title based on meeting purpose/topic\n"
    "   • Example: 'Remote Work Policy Review Meeting'\n"
    "   • Focus on the main subject discussed\n\n"
    
    "2. DATE & TIME: Extract ONLY if explicitly stated in transcript\n"
    "   • Look for: 'October 15', '10/15/2024', 'Monday morning', etc.\n"
    "   • If not found: use 'To be determined'\n\n"
    
    "3. ATTENDANTS: List ONLY people explicitly named\n"
    "   • Include: 'John Smith', 'Ms. Johnson', 'Dr. Lee'\n"
    "   • Exclude: department names, generic terms\n"
    "   • If no names mentioned: return empty array []\n\n"
    
    "4. PROJECT NAME: Extract ONLY if explicitly mentioned\n"
    "   • Must be stated as: 'Project X', 'the Y initiative', 'Z program'\n"
    "   • Do NOT infer from context\n"
    "   • If not found: 'To be determined'\n\n"
    
    "5. CUSTOMER: Extract ONLY if explicitly mentioned\n"
    "   • Look for: 'client ABC', 'customer XYZ', 'for company DEF'\n"
    "   • If not found: 'To be determined'\n\n"
    
    "6. TABLE OF CONTENT: Main topics discussed (ordered by importance)\n"
    "   • Be specific: 'Remote Work Policy' not 'Policy'\n"
    "   • Include: key decisions, issues, action items sections\n"
    "   • 5-10 items recommended\n\n"
    
    "7. MAIN CONTENT: Comprehensive but concise summary\n"
    "   • Include: meeting purpose, key discussions, decisions, outcomes\n"
    "   • Structure: Introduction → Discussion → Decisions → Next Steps\n"
    "   • 200-500 words\n"
    "   • Be factual, avoid interpretation\n\n"
    
    "CRITICAL: Do not invent information. Only extract what is explicitly stated.\n"
    "Return valid JSON only. No markdown code blocks.\n"
)

# ------------------ OPENAI CLIENT INIT ------------------
def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        if OpenAI is None:
            raise ImportError("Install OpenAI with: pip install openai")
        api_key = settings.openai_api_key
        if not api_key:
            # Try to get from environment variable
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
    # Try multiple sources for API key
    api_key = None
    
    # 1. Try from settings (from .env file via pydantic)
    api_key = settings.google_api_key
    
    # 2. Try from environment variable (direct)
    if not api_key:
        api_key = os.getenv("GOOGLE_API_KEY")
    
    # 3. Try from os.environ directly (case-insensitive)
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
    
    # Configure Gemini with API key (always configure to ensure it's set)
    genai.configure(api_key=api_key)
    return api_key

# ------------------ GEMINI CLIENT INIT ------------------
def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        if genai is None:
            raise ImportError("Install Google Generative AI with: pip install google-generativeai")
        _configure_gemini_api_key()
        
        # Try different FREE model names in order of preference
        # Only use free tier models
        model_names = [
            'gemini-1.5-flash-latest',  # Latest flash model (free)
            'gemini-1.5-flash',         # Flash model (free tier)
            'gemini-pro',               # Legacy free model
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
                available_models = []
                for model in genai.list_models():
                    if 'generateContent' in model.supported_generation_methods:
                        model_name = model.name.replace('models/', '')
                        available_models.append(model_name)
                        try:
                            _gemini_client = genai.GenerativeModel(model_name)
                            break
                        except Exception:
                            continue
                
                if _gemini_client is None and available_models:
                    try:
                        _gemini_client = genai.GenerativeModel(available_models[0])
                    except:
                        pass
            except Exception:
                pass
            
            if _gemini_client is None:
                raise RuntimeError(
                    f"Failed to initialize Gemini client with any model. "
                    f"Last error: {last_error}. "
                    f"Please check your GOOGLE_API_KEY and available models. "
                    f"Visit https://ai.google.dev/gemini-api/docs/models to see available models."
                )
    return _gemini_client

# ------------------ LLM GENERATION WITH FALLBACK ------------------
def _generate_with_llm(prompt: str, max_tokens: int = 2048) -> str:
    """Generate text with OpenAI API, fallback to Gemini if API key expired/invalid"""
    # Try OpenAI API first
    if OpenAI is not None and settings.openai_api_key:
        try:
            client = _get_openai_client()
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a precise meeting minutes assistant. Extract structured information from meeting transcripts. Return ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=max_tokens,
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            # Check if it's an API key related error
            error_str = str(e).lower()
            
            # Check for authentication/key errors
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
                except Exception:
                    raise RuntimeError(f"Both OpenAI API and Gemini failed. Please check your setup.")
            else:
                # Re-raise if it's an unexpected error
                raise
    
    try:
        return _generate_with_gemini(prompt, max_tokens)
    except Exception as e:
        raise RuntimeError(f"Gemini API failed: {e}")

# ------------------ GEMINI GENERATION ------------------
def _generate_with_gemini(prompt: str, max_tokens: int = 2048) -> str:
    """Generate text using Google Gemini API with fallback to different models"""
    global _gemini_client
    
    # Ensure API key is configured first
    try:
        _configure_gemini_api_key()
    except ValueError as key_error:
        raise RuntimeError(f"Gemini API key not configured: {key_error}")
    
    # Try different model names if current one fails
    # Try both free and available models
    model_names = [
        'gemini-1.5-flash-latest',  # Latest flash model
        'gemini-1.5-flash',         # Flash model
        'gemini-pro',               # Legacy model
        'gemini-1.0-pro',           # Alternative model name
        'gemini-1.5-flash-8b',      # Alternative flash variant
    ]
    
    try:
        for model in genai.list_models():
            if 'generateContent' in model.supported_generation_methods:
                model_name = model.name.replace('models/', '')
                if model_name not in model_names:
                    model_names.append(model_name)
    except Exception:
        pass
    
    # Prepare full prompt with system instructions
    full_prompt = (
        "You are a precise meeting minutes assistant. Extract structured information from meeting transcripts.\n"
        "CRITICAL: Return ONLY valid JSON. No markdown, no text before/after. Just pure JSON.\n\n"
        + prompt
    )
    
    last_error = None
    
    # First try with current model (if initialized)
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
                last_error = e
                _gemini_client = None
            else:
                # Other errors - raise immediately
                if "api key" in error_str or "authentication" in error_str or "403" in error_str or "401" in error_str:
                    raise ValueError(f"Gemini API key error: {e}")
                raise RuntimeError(f"Gemini API error: {e}")
    
    # Try other models (API key already configured above)
    for model_name in model_names:
        try:
            # Ensure API key is configured before creating each model
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
            elif "api key" in error_str or "authentication" in error_str or "403" in error_str or "401" in error_str or "no api_key" in error_str or "no api key" in error_str:
                # API key error - try to reconfigure and retry once
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
                except:
                    raise ValueError(f"Gemini API key error: {e}")
            else:
                # Other error - might work, but log it
                last_error = e
                continue
    
    if last_error:
        try:
            available_models = []
            for model in genai.list_models():
                if 'generateContent' in model.supported_generation_methods:
                    model_name = model.name.replace('models/', '')
                    if model_name not in model_names:
                        available_models.append(model_name)
            
            for model_name in available_models:
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
                        continue
                    elif "api key" in error_str or "authentication" in error_str:
                        raise ValueError(f"Gemini API key error: {e}")
                    else:
                        continue
        except Exception:
            pass
    
    # All models failed
    raise RuntimeError(
        f"Gemini API error: All models failed. Last error: {last_error}. "
        f"Please check your GOOGLE_API_KEY and available models. "
        f"Visit https://ai.google.dev/gemini-api/docs/models to see available models."
    )

# ------------------ MAIN SUMMARIZE FUNCTION ------------------
def summarize(sentences: List[str], language: str = "vi") -> Dict[str, Any]:
    """
    Generate structured meeting minutes from sentences using OpenAI API (with fallback to Gemini)
    Returns a dictionary with structured content
    """
    max_retries = 2
    max_tokens = 4096  # Tăng từ 2048 lên 4096 để tránh response bị cắt
    
    for attempt in range(max_retries + 1):
        try:
            # Tạo prompt với yêu cầu JSON ngắn gọn hơn nếu retry
            if attempt > 0:
                prompt = (
                    f"Language: {language}. "
                    + "IMPORTANT: Keep JSON response SHORT and CONCISE. "
                    + "Limit main_content to 300 words maximum. "
                    + "Limit table_of_content to 5-7 items maximum.\n\n"
                    + _SYSTEM_PROMPT
                    + "\n\nContent:\n"
                    + "\n".join(sentences)
                    + "\n\nRespond with ONLY valid JSON, no other text. Keep it SHORT:"
                )
            else:
                prompt = (
                    f"Language: {language}. "
                    + _SYSTEM_PROMPT
                    + "\n\nContent:\n"
                    + "\n".join(sentences)
                    + "\n\nRespond with ONLY valid JSON, no other text:"
                )
            
            text = _generate_with_llm(prompt, max_tokens=max_tokens)
            
            if text:
                # Try to parse JSON response
                try:
                    # Clean the response text (remove markdown formatting if present)
                    cleaned_text = text.strip()
                    if cleaned_text.startswith("```json"):
                        cleaned_text = cleaned_text[7:]
                    if cleaned_text.startswith("```"):
                        cleaned_text = cleaned_text[3:]
                    if cleaned_text.endswith("```"):
                        cleaned_text = cleaned_text[:-3]
                    
                    cleaned_text = cleaned_text.strip()
                    
                    # Try to extract JSON from text if embedded
                    json_match = re.search(r'\{.*\}', cleaned_text, re.DOTALL)
                    if json_match:
                        cleaned_text = json_match.group(0)
                    
                    if not cleaned_text.rstrip().endswith('}'):
                        if attempt < max_retries:
                            continue
                        else:
                            # Tìm vị trí string bị cắt và đóng nó
                            lines = cleaned_text.split('\n')
                            fixed_lines = []
                            in_string = False
                            for i, line in enumerate(lines):
                                fixed_lines.append(line)
                                # Đếm dấu ngoặc kép (đơn giản)
                                quote_count = line.count('"') - line.count('\\"')
                                if quote_count % 2 == 1:
                                    in_string = not in_string
                            
                            # Nếu đang trong string, đóng nó
                            if in_string:
                                fixed_lines[-1] = fixed_lines[-1].rstrip() + '"'
                            
                            # Đảm bảo kết thúc bằng }
                            if not fixed_lines[-1].rstrip().endswith('}'):
                                # Tìm dấu ngoặc nhọn cuối cùng
                                last_brace = cleaned_text.rfind('}')
                                if last_brace > 0:
                                    cleaned_text = cleaned_text[:last_brace+1]
                                else:
                                    # Thêm } nếu không có
                                    fixed_lines.append('}')
                            
                            cleaned_text = '\n'.join(fixed_lines)
                    
                    structured_data = json.loads(cleaned_text)
                    return structured_data
                except json.JSONDecodeError as e:
                    if attempt < max_retries:
                        continue
                    else:
                        raise RuntimeError(f"Failed to parse JSON from LLM response after {max_retries + 1} attempts: {e}")
            
            raise RuntimeError("LLM returned empty response")
            
        except RuntimeError as e:
            if "Failed to parse JSON" in str(e) and attempt < max_retries:
                continue
            raise
        except Exception as e:
            if attempt < max_retries:
                continue
            raise RuntimeError(f"Failed to summarize meeting minutes: {e}")
    
    raise RuntimeError("Failed to summarize meeting minutes after all retry attempts")
