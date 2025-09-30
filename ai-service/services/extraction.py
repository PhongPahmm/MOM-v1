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
    "action_items (array of {description, owner?, due_date?, priority?})."
)

def extract_actions_and_decisions(sentences: List[str]) -> Tuple[List[ActionItem], List[Decision]]:
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
    prompt = _EXTRACTION_PROMPT + "\n\nContent:\n" + "\n".join(sentences)
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
