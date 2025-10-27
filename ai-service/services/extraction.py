import json
from typing import List, Tuple

from schemas.mom import ActionItem, Decision
from core.config import settings

try:
    import google.generativeai as genai  # type: ignore
except Exception:  # pragma: no cover
    genai = None  # type: ignore

_EXTRACTION_PROMPT = (
    "Extract decisions and action items from the meeting content.\n"
    "Return strict JSON with keys: decisions (array of {text, owner?}), "
    "action_items (array of {description, owner?, due_date?, priority?}).\n\n"
    "IMPORTANT RULES for extracting action items:\n"
    "1. Look for explicit task assignments like: 'John will do X', 'Mary needs to Y', 'Please assign Z to Sarah'\n"
    "2. Look for action items with clear ownership: 'I will handle this', 'Team A should complete', 'Someone needs to'\n"
    "3. Extract owner names from speaker labels, participant names, or explicitly mentioned people\n"
    "4. If no clear owner is mentioned, leave owner field as null\n"
    "5. Look for due dates in formats like: 'by Friday', 'next week', 'before the meeting', 'within 2 days'\n"
    "6. Identify priority levels: 'urgent', 'high priority', 'asap', 'low priority', 'when possible'\n"
    "7. Focus on actionable items that require someone to do something specific\n\n"
    "Examples of good action items:\n"
    "- 'John will prepare the presentation slides by next Monday' -> {description: 'Prepare the presentation slides', owner: 'John', due_date: 'next Monday'}\n"
    "- 'We need someone to contact the client' -> {description: 'Contact the client', owner: null}\n"
    "- 'I'll follow up with the vendor' -> {description: 'Follow up with the vendor', owner: [speaker name]}\n"
    "- 'Sarah, can you handle the budget review?' -> {description: 'Handle the budget review', owner: 'Sarah'}\n"
    "- 'The marketing team should update the website' -> {description: 'Update the website', owner: 'marketing team'}\n"
    "- 'Let's assign this to Mike for next week' -> {description: 'Assign task to Mike', owner: 'Mike', due_date: 'next week'}\n\n"
    "When you see speaker information, use the speaker names to identify who is saying 'I will do X' or 'I'll handle Y'.\n"
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
    
    resp = model.generate_content(prompt)
    text = getattr(resp, "text", "") or "{}"

    try:
        data = json.loads(text)
    except Exception:
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
