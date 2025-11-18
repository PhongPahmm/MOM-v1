import json
import re
from json import JSONDecodeError
from typing import List, Tuple

from schemas.mom import ActionItem, Decision
from core.config import settings

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

_openai_client = None
_gemini_client = None

# ------------------ PROMPT ĐƯỢC RÚT GỌN & TỐI ƯU ------------------
_EXTRACTION_PROMPT = """Extract action items and decisions from this meeting transcript. Return ONLY valid JSON, no other text.

Required JSON format:
{
  "action_items": [
    {"description": "task description", "owner": "name or null", "due_date": "date or null", "priority": "priority or null"}
  ],
  "decisions": [
    {"text": "decision text", "owner": "name or null"}
  ]
}

Extract:
- Action items: tasks assigned (look for "will", "needs to", "to do", "by [date]")
- Decisions: agreements (look for "decided", "agreed", "approved")
- Owner: person's name if mentioned
- Due date: dates like "november 6, 2025", "tonight", "by 5 pm today"

Transcript:
"""

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
        print("✅ OpenAI client initialized.")
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
        
        # Try different model names in order of preference
        # Prioritize newer, faster models first
        model_names = [
            'gemini-2.5-flash',         # Newest flash model (fastest)
            'gemini-2.0-flash',         # Flash model v2
            'gemini-1.5-flash-latest',  # Latest flash model
            'gemini-1.5-flash',         # Flash model
            'gemini-pro',               # Legacy model
        ]
        
        _gemini_client = None
        last_error = None
        
        for model_name in model_names:
            try:
                _gemini_client = genai.GenerativeModel(model_name)
                print(f"✅ Gemini client initialized (using {model_name}).")
                break
            except Exception as e:
                last_error = e
                continue
        
        if _gemini_client is None:
            # If all models failed, try to list ALL available models and find one that works
            try:
                print("⚠️ All predefined models failed. Listing available Gemini models...")
                available_models = []
                for model in genai.list_models():
                    if 'generateContent' in model.supported_generation_methods:
                        model_name = model.name.replace('models/', '')
                        available_models.append(model_name)
                        print(f"   Available model: {model_name}")
                        
                        # Try to use any available model (prioritize flash models for free tier)
                        try:
                            _gemini_client = genai.GenerativeModel(model_name)
                            print(f"✅ Gemini client initialized (using {model_name}).")
                            break
                        except Exception as test_error:
                            # If initialization fails, try next model
                            continue
                
                if _gemini_client is None and available_models:
                    print(f"⚠️ Found {len(available_models)} models but none worked. Trying first available model anyway...")
                    try:
                        _gemini_client = genai.GenerativeModel(available_models[0])
                        print(f"✅ Gemini client initialized (using {available_models[0]} - may fail on first use).")
                    except:
                        pass
            except Exception as list_error:
                print(f"⚠️ Could not list models: {list_error}")
            
            if _gemini_client is None:
                raise RuntimeError(
                    f"Failed to initialize Gemini client with any model. "
                    f"Last error: {last_error}. "
                    f"Please check your GOOGLE_API_KEY and available models. "
                    f"Visit https://ai.google.dev/gemini-api/docs/models to see available models."
                )
    return _gemini_client

# ------------------ GEMINI GENERATION ------------------
def _generate_with_gemini(prompt: str, max_tokens: int = 1500) -> str:
    """Generate text using Google Gemini API with fallback to different models"""
    global _gemini_client
    
    # Ensure API key is configured first
    try:
        _configure_gemini_api_key()
    except ValueError as key_error:
        raise RuntimeError(f"Gemini API key not configured: {key_error}")
    
    # Try different model names if current one fails
    # Prioritize newer, faster models first
    model_names = [
        'gemini-2.5-flash',         # Newest flash model (fastest)
        'gemini-2.0-flash',         # Flash model v2
        'gemini-1.5-flash-latest',  # Latest flash model
        'gemini-1.5-flash',         # Flash model
        'gemini-pro',               # Legacy model
    ]
    
    # Skip listing models if we already have a working client
    # Only list models if all predefined models fail (to save time)
    
    # Prepare full prompt
    full_prompt = (
        "You extract structured action items and decisions from meeting transcripts.\n"
        "Return ONLY valid JSON, no other text.\n\n"
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
            # If it's a 404 or model not found error, try other models
            if "404" in error_str or "not found" in error_str:
                print(f"⚠️ Model not found, trying other models...")
                last_error = e
                # Reset client to try other models
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
            # Save working model for next time
            _gemini_client = model
            print(f"✅ Using Gemini model: {model_name}")
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
                    print(f"✅ Using Gemini model: {model_name} (after reconfiguring API key)")
                    return response.text.strip()
                except:
                    raise ValueError(f"Gemini API key error: {e}")
            else:
                # Other error - might work, but log it
                last_error = e
                continue
    
    # All predefined models failed - try listing and using available models (only if needed)
    if last_error and _gemini_client is None:
        try:
            print("⚠️ All predefined models failed. Listing available Gemini models...")
            available_models = []
            # Only list models once and cache the first working one
            for model in genai.list_models():
                if 'generateContent' in model.supported_generation_methods:
                    model_name = model.name.replace('models/', '')
                    if model_name not in model_names:  # Avoid retrying models we already tried
                        available_models.append(model_name)
                        # Try first few models immediately (don't list all)
                        if len(available_models) <= 3:  # Only try first 3 to save time
                            try:
                                _configure_gemini_api_key()
                                model_obj = genai.GenerativeModel(model_name)
                                response = model_obj.generate_content(
                                    full_prompt,
                                    generation_config=genai.types.GenerationConfig(
                                        temperature=0.1,
                                        max_output_tokens=max_tokens,
                                    )
                                )
                                # Save working model for next time
                                _gemini_client = model_obj
                                print(f"✅ Using Gemini model: {model_name}")
                                return response.text.strip()
                            except Exception as e:
                                error_str = str(e).lower()
                                if "404" in error_str or "not found" in error_str:
                                    continue
                                elif "api key" in error_str or "authentication" in error_str:
                                    raise ValueError(f"Gemini API key error: {e}")
                                else:
                                    continue
                        else:
                            break  # Stop listing after first 3 attempts
        except Exception as list_error:
            print(f"⚠️ Could not list or use additional models: {list_error}")
    
    # All models failed
    raise RuntimeError(
        f"Gemini API error: All models failed. Last error: {last_error}. "
        f"Please check your GOOGLE_API_KEY and available models. "
        f"Visit https://ai.google.dev/gemini-api/docs/models to see available models."
    )

# ------------------ LLM WRAPPER WITH FALLBACK ------------------
def _generate_with_llm(prompt: str, max_tokens: int = 1500) -> str:
    """Generate text with OpenAI API, fallback to Gemini if API key expired/invalid"""
    # Try OpenAI API first
    if OpenAI is not None and settings.openai_api_key:
        try:
            client = _get_openai_client()
            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You extract structured action items and decisions from meeting transcripts. Return ONLY valid JSON."},
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
                # API key expired, invalid, or quota exceeded - fallback to Gemini
                print(f"⚠️ OpenAI API error ({e}). Falling back to Gemini...")
                return _generate_with_gemini(prompt, max_tokens)
            elif isinstance(e, ValueError) and "Missing OPENAI_API_KEY" in str(e):
                # Missing API key - try Gemini
                print(f"⚠️ OpenAI API key not found. Using Gemini...")
                return _generate_with_gemini(prompt, max_tokens)
            elif APIError is not None and isinstance(e, APIError):
                # Other API errors - try Gemini as fallback
                print(f"⚠️ OpenAI API error ({e}). Falling back to Gemini...")
                try:
                    return _generate_with_gemini(prompt, max_tokens)
                except Exception as gemini_error:
                    print(f"⚠️ Gemini also failed: {gemini_error}")
                    raise RuntimeError(f"Both OpenAI API and Gemini failed. Please check your setup.")
            else:
                # Re-raise if it's an unexpected error
                raise
    
    # No OpenAI API key or OpenAI not available - use Gemini
    print(f"ℹ️ Using Gemini API...")
    try:
        return _generate_with_gemini(prompt, max_tokens)
    except Exception as e:
        print(f"⚠️ Gemini failed: {e}")
        raise RuntimeError(f"Gemini API failed: {e}")

# ------------------ CLEAN JSON ------------------
def _try_parse_json(raw_text: str):
    raw = raw_text.strip().replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("No JSON found in model output.")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise JSONDecodeError(exc.msg, exc.doc, exc.pos)

# ------------------ MAIN EXTRACT FUNCTION ------------------
def extract_actions_and_decisions(sentences: List[str], diarization_data: List[Tuple[str, str]] = None) -> Tuple[List[ActionItem], List[Decision]]:
    """Extract all action items and decisions using OpenAI API -> Gemini fallback"""
    text = " ".join(sentences)
    base_prompt = _EXTRACTION_PROMPT + "\n" + text.strip()
    prompt = base_prompt

    raw_response = ""
    attempts = 0
    max_attempts = 3

    while attempts < max_attempts:
        try:
            print("🚀 Extracting with LLM...")
            raw_response = _generate_with_llm(prompt)
            data = _try_parse_json(raw_response)
            break
        except (ValueError, JSONDecodeError) as parse_error:
            attempts += 1
            trimmed_response = raw_response.strip().replace("\n", " ")[:400]
            print(f"⚠️ JSON parse failed (attempt {attempts}/{max_attempts}): {parse_error}")
            if trimmed_response:
                print(f"🔍 Raw response (trimmed): {trimmed_response}")

            if attempts >= max_attempts:
                print(f"❌ LLM extraction failed after {attempts} attempts ({parse_error}).")
                raise RuntimeError(f"Failed to extract actions and decisions: {parse_error}")

            prompt = (
                base_prompt
                + "\n\nYour previous response was invalid JSON. "
                  "Reply again using ONLY valid JSON that matches the required schema "
                  "without additional text, comments, or trailing commas."
            )
    else:
        raise RuntimeError("Failed to extract actions and decisions: Unknown error during parsing.")

    # --- Validate ---
    action_items, decisions = [], []
    for a in data.get("action_items", []):
        if not a.get("description"):
            continue
        action_items.append(ActionItem(
            description=a["description"].strip(),
            owner=(a.get("owner") or None),
            due_date=(a.get("due_date") or None),
            priority=(a.get("priority") or None)
        ))
    for d in data.get("decisions", []):
        if not d.get("text"):
            continue
        decisions.append(Decision(
            text=d["text"].strip(),
            owner=(d.get("owner") or None)
        ))

    print(f"✅ Extracted {len(action_items)} action items, {len(decisions)} decisions.")
    return action_items[:25], decisions[:25]
