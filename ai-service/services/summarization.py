from typing import List, Dict, Any
import json

try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None  # type: ignore

from core.config import settings

_SYSTEM_PROMPT = (
    "You are an AI assistant specialized in creating structured meeting minutes. "
    "Based on the meeting content, extract and organize the following information:\n\n"
    "1. TITLE: Create a clear, descriptive title for the meeting\n"
    "2. DATE & TIME: Extract date and time if mentioned, or use 'To be determined' if not found\n"
    "3. ATTENDANTS: List all people mentioned as participants, speakers, or attendees\n"
    "4. PROJECT NAME: Identify the project name or topic being discussed\n"
    "5. CUSTOMER: Identify the customer or client if mentioned\n"
    "6. TABLE OF CONTENT: Create a structured outline of main topics discussed\n"
    "7. MAIN CONTENT: Provide a comprehensive summary of the meeting content\n\n"
    "Format your response as a JSON object with these exact keys: title, date, time, attendants, project_name, customer, table_of_content, main_content."
)

def summarize(sentences: List[str], language: str = "vi") -> Dict[str, Any]:
    """
    Generate structured meeting minutes from sentences
    Returns a dictionary with structured content
    """
    if genai is None:
        print(
            "Warning: Google Generative AI library is not installed. "
            "Please install it with: pip install google-generativeai"
        )
        return _get_default_structured_content(sentences)

    # 🔑 Lấy từ settings
    google_api_key = settings.google_api_key
    if not google_api_key:
        print(
            "Warning: Google API key is not configured. "
            "Please set GOOGLE_API_KEY in your environment variables or .env file. "
            "Get your API key from: https://makersuite.google.com/app/apikey"
        )
        return _get_default_structured_content(sentences)

    try:
        genai.configure(api_key=google_api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = (
            f"Language: {language}. "
            + _SYSTEM_PROMPT
            + "\n\nContent:\n"
            + "\n".join(sentences)
        )
        resp = model.generate_content(prompt)
        text = getattr(resp, "text", None)
        
        if text:
            # Try to parse JSON response
            try:
                # Clean the response text (remove markdown formatting if present)
                cleaned_text = text.strip()
                if cleaned_text.startswith("```json"):
                    cleaned_text = cleaned_text[7:]
                if cleaned_text.endswith("```"):
                    cleaned_text = cleaned_text[:-3]
                
                structured_data = json.loads(cleaned_text)
                return structured_data
            except json.JSONDecodeError:
                print(f"Failed to parse JSON response: {text}")
                return _get_fallback_structured_content(text, sentences)
        
        return _get_default_structured_content(sentences)
        
    except Exception as e:
        print(f"Error in summarization: {e}")
        return _get_default_structured_content(sentences)

def _get_default_structured_content(sentences: List[str]) -> Dict[str, Any]:
    """Fallback structured content when AI is not available"""
    return {
        "title": "Meeting Minutes",
        "date": "To be determined",
        "time": "To be determined", 
        "attendants": [],
        "project_name": "To be determined",
        "customer": "To be determined",
        "table_of_content": [f"Topic {i+1}" for i in range(min(5, len(sentences)))],
        "main_content": " ".join(sentences[:5])
    }

def _get_fallback_structured_content(ai_response: str, sentences: List[str]) -> Dict[str, Any]:
    """Fallback when JSON parsing fails but we have AI response"""
    return {
        "title": "Meeting Minutes",
        "date": "To be determined",
        "time": "To be determined",
        "attendants": [],
        "project_name": "To be determined", 
        "customer": "To be determined",
        "table_of_content": ["Main Discussion Points"],
        "main_content": ai_response if ai_response else " ".join(sentences[:5])
    }
