import json
import re
import time
from typing import List, Tuple

from schemas.mom import ActionItem, Decision
from core.config import settings

try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None  # type: ignore

_EXTRACTION_PROMPT = (
    "You are an AI assistant specialized in extracting action items and decisions from meeting transcripts.\n"
    "IMPORTANT: Return ONLY valid JSON, no markdown formatting, no explanations. Start directly with { and end with }.\n\n"
    "Return a JSON object with exactly these keys:\n"
    "- decisions: array of {text: string, owner?: string | null}\n"
    "- action_items: array of {description: string, owner?: string | null, due_date?: string | null, priority?: string | null}\n\n"
    "RULES for extracting action items:\n"
    "1. Look for explicit task assignments like: 'John will do X', 'Mary needs to Y', 'Please assign Z to Sarah'\n"
    "2. Look for action items with clear ownership: 'I will handle this', 'Team A should complete', 'Someone needs to'\n"
    "3. Extract owner names from speaker labels, participant names, or explicitly mentioned people\n"
    "4. If no clear owner is mentioned, leave owner field as null\n"
    "5. Look for due dates in formats like: 'by Friday', 'next week', 'before the meeting', 'within 2 days'\n"
    "6. Identify priority levels: 'urgent', 'high priority', 'asap', 'low priority', 'when possible'\n"
    "7. Focus on actionable items that require someone to do something specific\n\n"
    "RULES for extracting decisions:\n"
    "1. Look for statements like: 'We decided to...', 'The decision is...', 'Let's go with...', 'We agreed to...'\n"
    "2. Identify who made the decision if mentioned\n"
    "3. Extract the decision text clearly\n\n"
    "Examples:\n"
    "Input: 'John will prepare the presentation slides by next Monday'\n"
    "Output: {\"action_items\": [{\"description\": \"Prepare the presentation slides\", \"owner\": \"John\", \"due_date\": \"next Monday\"}], \"decisions\": []}\n\n"
    "Input: 'We decided to use the new framework'\n"
    "Output: {\"decisions\": [{\"text\": \"Use the new framework\"}], \"action_items\": []}\n\n"
    "When you see speaker information, use the speaker names to identify who is saying 'I will do X' or 'I'll handle Y'.\n"
    "Always return valid JSON only, no markdown code blocks, no explanations before or after.\n"
)

def extract_actions_and_decisions(sentences: List[str], diarization_data: List[Tuple[str, str]] = None) -> Tuple[List[ActionItem], List[Decision]]:
    if genai is None:
        print(
            "Warning: Google Generative AI library is not installed. "
            "Please install it with: pip install google-generativeai"
        )
        return [], []

    google_api_key = settings.google_api_key
    if not google_api_key:
        print(
            "Warning: Google API key is not configured. "
            "Please set GOOGLE_API_KEY in your environment variables or .env file. "
            "Get your API key from: https://makersuite.google.com/app/apikey"
        )
        return [], []

    try:
        genai.configure(api_key=google_api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        
        # Build enhanced prompt with diarization data
        content_section = "\n".join(sentences)
        
        if diarization_data:
            speaker_info = "\nSpeaker Information:\n"
            for speaker, text in diarization_data:
                speaker_info += f"- {speaker}: {text}\n"
            prompt = _EXTRACTION_PROMPT + f"\n\n{speaker_info}\n\nContent:\n{content_section}"
        else:
            prompt = _EXTRACTION_PROMPT + "\n\nContent:\n" + content_section
        
        # Retry logic với exponential backoff cho rate limit errors
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                resp = model.generate_content(prompt)
                text = getattr(resp, "text", "") or "{}"
                
                # Clean response text - remove markdown formatting if present
                cleaned_text = text.strip()
                if cleaned_text.startswith("```json"):
                    cleaned_text = cleaned_text[7:]  # Remove ```json
                elif cleaned_text.startswith("```"):
                    cleaned_text = cleaned_text[3:]  # Remove ```
                
                if cleaned_text.endswith("```"):
                    cleaned_text = cleaned_text[:-3]  # Remove closing ```
                
                cleaned_text = cleaned_text.strip()
                
                # Try to extract JSON from the response if it's embedded in text
                if not cleaned_text.startswith("{"):
                    # Try to find JSON object in the text
                    json_match = re.search(r'\{.*\}', cleaned_text, re.DOTALL)
                    if json_match:
                        cleaned_text = json_match.group(0)
                
                try:
                    data = json.loads(cleaned_text)
                    print(f"Successfully parsed extraction response: {len(data.get('action_items', []))} action items, {len(data.get('decisions', []))} decisions")
                except json.JSONDecodeError as json_error:
                    print(f"Failed to parse JSON from extraction response. Error: {json_error}")
                    print(f"Response text: {cleaned_text[:500]}...")  # Log first 500 chars
                    # Try to extract partial data or return empty
                    data = {"decisions": [], "action_items": []}

                decisions: List[Decision] = []
                for d in data.get("decisions", []) or []:
                    decisions.append(Decision(text=d.get("text", ""), owner=d.get("owner")))

                actions: List[ActionItem] = []
                for a in data.get("action_items", []) or []:
                    actions.append(
                        ActionItem(
                            description=a.get("description", ""),
                            owner=a.get("owner"),
                            due_date=a.get("due_date"),
                            priority=a.get("priority"),
                        )
                    )

                return actions, decisions
                
            except Exception as api_error:
                error_message = str(api_error).lower()
                # Kiểm tra xem có phải lỗi rate limit/quota không
                if "429" in error_message or "resource exhausted" in error_message or "quota" in error_message:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)  # Exponential backoff: 2s, 4s, 8s
                        print(f"Rate limit error (attempt {attempt + 1}/{max_retries}). Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"Rate limit error after {max_retries} attempts. Returning empty lists.")
                        return [], []
                else:
                    # Lỗi khác, không retry
                    raise
        
        return [], []
        
    except Exception as e:
        print(f"Error in extraction: {e}")
        return [], []
