import json
import re
from typing import List, Tuple

from schemas.mom import ActionItem, Decision
from core.config import settings

try:
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import torch
except ImportError:
    AutoTokenizer = None
    AutoModelForCausalLM = None
    torch = None

# Global model cache
_llm_model = None
_llm_tokenizer = None

_EXTRACTION_PROMPT = (
    "You are a precise meeting minutes assistant. Extract action items and decisions from meeting transcripts.\n"
    "CRITICAL: Return ONLY valid JSON. No markdown, no text before/after. Just pure JSON starting with { and ending with }.\n\n"
    
    "REQUIRED JSON FORMAT:\n"
    "{\n"
    '  "action_items": [{"description": "string", "owner": "string or null", "due_date": "string or null", "priority": "string or null"}],\n'
    '  "decisions": [{"text": "string", "owner": "string or null"}]\n'
    "}\n\n"
    
    "ACTION ITEMS - What to extract:\n"
    "• Explicit assignments: 'HR will draft policy by October 15'\n"
    "  → Extract: owner='HR', description='draft policy', due_date='October 15'\n"
    "• Task commitments: 'Finance needs to finalize budget by October 20'\n"
    "  → Extract: owner='Finance', description='finalize budget', due_date='October 20'\n"
    "• Must/Should statements: 'IT must enforce VPN requirements'\n"
    "  → Extract: owner='IT', description='enforce VPN requirements'\n"
    "• Multiple tasks in one sentence: Extract each separately\n"
    "• ONLY extract clear, actionable tasks with verbs (draft, finalize, schedule, enforce, etc.)\n"
    "• DO NOT extract general statements or descriptions\n\n"
    
    "DECISIONS - What to extract:\n"
    "• Proposals accepted: 'proposal is to introduce 3-day remote work'\n"
    "  → Extract: text='introduce 3-day remote work policy'\n"
    "• Agreements: 'we agreed to provide home office allowance'\n"
    "  → Extract: text='provide home office allowance'\n"
    "• Policy changes: 'policy will emphasize output-based metrics'\n"
    "  → Extract: text='emphasize output-based metrics'\n"
    "• Consensus: 'consensus was that allowance is investment'\n"
    "  → Extract: text='home office allowance is investment in productivity'\n"
    "• Implementation plans: 'guideline will be rolled out as pilot'\n"
    "  → Extract: text='roll out guideline as 3-month pilot'\n\n"
    
    "CRITICAL RULES:\n"
    "1. Keep descriptions concise (under 100 characters)\n"
    "2. Keep decision text concise (under 150 characters)\n"
    "3. Extract owner names exactly as mentioned (HR, Finance, IT, Managers, etc.)\n"
    "4. Extract due dates exactly as stated (october 15, end of october, november 1, etc.)\n"
    "5. If no owner/date mentioned, use null\n"
    "6. If no action items or decisions found, return empty arrays\n"
    "7. Do not invent or assume information not in transcript\n\n"
    
    "EXAMPLES:\n\n"
    
    "Example 1:\n"
    'Input: "Action items were assigned. HR will draft the policy by October 15. Finance will finalize budget by October 20."\n'
    "Output:\n"
    "{\n"
    '  "action_items": [\n'
    '    {"description": "draft the policy", "owner": "HR", "due_date": "October 15", "priority": null},\n'
    '    {"description": "finalize budget", "owner": "Finance", "due_date": "October 20", "priority": null}\n'
    '  ],\n'
    '  "decisions": []\n'
    "}\n\n"
    
    "Example 2:\n"
    'Input: "We decided to implement a 3-day remote work policy. The proposal includes mandatory team days twice per month."\n'
    "Output:\n"
    "{\n"
    '  "action_items": [],\n'
    '  "decisions": [\n'
    '    {"text": "implement 3-day remote work policy", "owner": null},\n'
    '    {"text": "mandatory team days twice per month", "owner": null}\n'
    '  ]\n'
    "}\n\n"
    
    "Example 3:\n"
    'Input: "Managers must schedule weekly check-ins starting November 1. We agreed to use output-based metrics."\n'
    "Output:\n"
    "{\n"
    '  "action_items": [\n'
    '    {"description": "schedule weekly check-ins", "owner": "Managers", "due_date": "November 1", "priority": null}\n'
    '  ],\n'
    '  "decisions": [\n'
    '    {"text": "use output-based metrics", "owner": null}\n'
    '  ]\n'
    "}\n\n"
    
    "Now extract from the following transcript. Return ONLY the JSON object:\n"
)

def _get_llm_model():
    """Lazy load LLM model to avoid loading on import"""
    global _llm_model, _llm_tokenizer
    
    if _llm_model is None or _llm_tokenizer is None:
        if AutoTokenizer is None or AutoModelForCausalLM is None or torch is None:
            raise ImportError(
                "Transformers or PyTorch is not installed. Please install with: pip install transformers torch"
            )
        
        model_name = settings.llm_model_name or "google/gemma-2b-it"
        print(f"Loading LLM model ({model_name})... This may take a while on first run.")
        
        _llm_tokenizer = AutoTokenizer.from_pretrained(model_name)
        _llm_model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device_map="auto" if torch.cuda.is_available() else None,
            low_cpu_mem_usage=True
        )
        
        if not torch.cuda.is_available():
            _llm_model = _llm_model.to("cpu")
        
        print(f"LLM model loaded successfully.")
    
    return _llm_model, _llm_tokenizer

def _generate_with_llm(prompt: str, max_new_tokens: int = 1024) -> str:
    """Generate text using local LLM with optimized parameters for accuracy"""
    model, tokenizer = _get_llm_model()
    
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=6144)
    
    if torch.cuda.is_available():
        inputs = {k: v.to("cuda") for k, v in inputs.items()}
    
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=0.2,  # Lower temperature for more accurate, deterministic output
            do_sample=True,
            top_p=0.85,  # Slightly lower for more focused output
            top_k=40,  # Add top-k sampling for better quality
            repetition_penalty=1.15,  # Prevent repetition
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id
        )
    
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    
    # Remove the input prompt from response
    if response.startswith(prompt):
        response = response[len(prompt):].strip()
    
    return response

def _validate_and_clean_extraction(data: dict) -> dict:
    """Validate and clean extracted data to ensure accuracy"""
    cleaned = {
        "action_items": [],
        "decisions": []
    }
    
    # Validate and clean action items
    for item in data.get("action_items", []) or []:
        description = item.get("description", "").strip()
        owner = item.get("owner")
        due_date = item.get("due_date")
        priority = item.get("priority")
        
        # Skip invalid items
        if not description or len(description) < 5:
            continue
        
        # Clean description - must contain action verb
        action_verbs = ['draft', 'finalize', 'prepare', 'schedule', 'enforce', 'implement', 
                       'create', 'review', 'update', 'submit', 'complete', 'monitor',
                       'analyze', 'develop', 'coordinate', 'organize', 'send', 'provide']
        
        has_action = any(verb in description.lower() for verb in action_verbs)
        if not has_action:
            continue
        
        # Limit length
        if len(description) > 200:
            description = description[:200]
        
        # Clean owner
        if owner and isinstance(owner, str):
            owner = owner.strip()
            if len(owner) > 50 or owner.lower() in ['null', 'none', 'n/a', '']:
                owner = None
        else:
            owner = None
        
        # Clean due_date
        if due_date and isinstance(due_date, str):
            due_date = due_date.strip()
            if len(due_date) > 50 or due_date.lower() in ['null', 'none', 'n/a', '']:
                due_date = None
        else:
            due_date = None
        
        cleaned["action_items"].append({
            "description": description,
            "owner": owner,
            "due_date": due_date,
            "priority": priority
        })
    
    # Validate and clean decisions
    for item in data.get("decisions", []) or []:
        text = item.get("text", "").strip()
        owner = item.get("owner")
        
        # Skip invalid decisions
        if not text or len(text) < 10:
            continue
        
        # Limit length
        if len(text) > 250:
            text = text[:250]
        
        # Clean owner
        if owner and isinstance(owner, str):
            owner = owner.strip()
            if len(owner) > 50 or owner.lower() in ['null', 'none', 'n/a', '']:
                owner = None
        else:
            owner = None
        
        cleaned["decisions"].append({
            "text": text,
            "owner": owner
        })
    
    return cleaned

def _extract_with_rules(text: str) -> Tuple[List[ActionItem], List[Decision]]:
    """Rule-based extraction as fallback"""
    actions: List[ActionItem] = []
    decisions: List[Decision] = []
    
    # Special handling for "Action items were assigned" section
    action_section_match = re.search(
        r'Action items were assigned\.(.*?)(?:Before closing|The next|$)',
        text,
        re.IGNORECASE | re.DOTALL
    )
    
    if action_section_match:
        action_section = action_section_match.group(1)
        
        # Extract specific action items from this section
        # Pattern: "X will Y by date"
        specific_patterns = [
            r'(\w+(?:\s+\w+)?)\s+will\s+([\w\s]+?)\s+by\s+((?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d+|the end of \w+|\d+\/\d+)',
            r'(\w+(?:\s+\w+)?)\s+will\s+([\w\s]+?)\s+starting\s+((?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d+|the end of \w+|\w+\s+\d+)',
        ]
        
        for pattern in specific_patterns:
            matches = re.finditer(pattern, action_section, re.IGNORECASE)
            for match in matches:
                owner = match.group(1).strip().title()
                description = match.group(2).strip()
                due_date = match.group(3).strip()
                
                # Clean up description - remove extra words
                description = re.sub(r'\s+', ' ', description).strip()
                
                if len(description) > 5 and len(owner) < 30:
                    actions.append(ActionItem(
                        description=description,
                        owner=owner,
                        due_date=due_date,
                        priority=None
                    ))
    
    # Split into sentences for general extraction
    sentences = re.split(r'[.!?]+', text)
    
    # Extract more action items from general text
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence or len(sentence) < 20:
            continue
        
        # Skip if already in action section
        if action_section_match and sentence in action_section_match.group(0):
            continue
            
        # Pattern: "X will Y" (but not too long)
        match = re.search(
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+will\s+([\w\s]{10,80}?)(?:\s+by|\s+starting|\s+to|\.|$)',
            sentence
        )
        if match:
            owner = match.group(1).strip()
            description = match.group(2).strip()
            
            # Check for due date in remaining sentence
            due_date = None
            due_match = re.search(
                r'by\s+((?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d+|the end of \w+|\d+\/\d+)',
                sentence,
                re.IGNORECASE
            )
            if due_match:
                due_date = due_match.group(1)
            
            if len(description) > 5:
                actions.append(ActionItem(
                    description=description,
                    owner=owner,
                    due_date=due_date,
                    priority=None
                ))
        
        # Pattern: "X must/should Y"
        match = re.search(
            r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:must|should)\s+([\w\s]{10,80}?)(?:\s+by|\s+to|\.|$)',
            sentence
        )
        if match:
            owner = match.group(1).strip()
            description = match.group(2).strip()
            
            if len(description) > 5:
                actions.append(ActionItem(
                    description=description,
                    owner=owner,
                    due_date=None,
                    priority=None
                ))
    
    # Extract decisions
    decision_keywords = [
        'proposal is to', 'proposal includes', 'policy will', 
        'guideline will', 'decided to', 'agreed to', 
        'consensus was', 'will be rolled out'
    ]
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence or len(sentence) < 20:
            continue
            
        for keyword in decision_keywords:
            if keyword in sentence.lower():
                # Extract the decision part
                parts = sentence.lower().split(keyword)
                if len(parts) > 1:
                    decision_text = parts[1].strip()
                    # Clean up and limit length
                    decision_text = re.sub(r'\s+', ' ', decision_text)
                    
                    # Remove trailing incomplete phrases
                    decision_text = re.split(r'\s+(?:the|this|it|and|but|however)\s+', decision_text)[0]
                    
                    if len(decision_text) > 15 and len(decision_text) < 200:
                        decisions.append(Decision(
                            text=decision_text.strip(),
                            owner=None
                        ))
                break
    
    # Also extract from "To solve this" or "In response" sections
    response_patterns = [
        r'To solve this,\s+(.{20,200}?)(?:\.|$)',
        r'In response,\s+(.{20,200}?)(?:\.|$)',
        r'To address this,\s+(.{20,200}?)(?:\.|$)',
        r'To compensate,\s+(.{20,200}?)(?:\.|$)',
    ]
    
    for pattern in response_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            decision_text = match.group(1).strip()
            decision_text = re.sub(r'\s+', ' ', decision_text)
            if len(decision_text) > 15:
                decisions.append(Decision(
                    text=decision_text,
                    owner=None
                ))
    
    # Remove duplicates
    unique_actions = []
    seen_descriptions = set()
    for action in actions:
        desc_lower = action.description.lower()
        if desc_lower not in seen_descriptions:
            unique_actions.append(action)
            seen_descriptions.add(desc_lower)
    
    unique_decisions = []
    seen_texts = set()
    for decision in decisions:
        text_lower = decision.text.lower()[:50]  # Compare first 50 chars
        if text_lower not in seen_texts:
            unique_decisions.append(decision)
            seen_texts.add(text_lower)
    
    return unique_actions[:15], unique_decisions[:15]  # Limit to 15 each

def extract_actions_and_decisions(sentences: List[str], diarization_data: List[Tuple[str, str]] = None) -> Tuple[List[ActionItem], List[Decision]]:
    if AutoTokenizer is None or AutoModelForCausalLM is None:
        print(
            "Warning: Transformers library is not installed. Using rule-based extraction."
        )
        full_text = " ".join(sentences)
        return _extract_with_rules(full_text)

    try:
        # Build enhanced prompt with diarization data
        content_section = "\n".join(sentences)
        
        if diarization_data:
            speaker_info = "\nSpeaker Information:\n"
            for speaker, text in diarization_data:
                speaker_info += f"- {speaker}: {text}\n"
            prompt = _EXTRACTION_PROMPT + f"\n\n{speaker_info}\n\nContent:\n{content_section}\n\nRespond with ONLY valid JSON:"
        else:
            prompt = _EXTRACTION_PROMPT + "\n\nContent:\n" + content_section + "\n\nRespond with ONLY valid JSON:"
        
        print("Extracting action items and decisions with local LLM...")
        text = _generate_with_llm(prompt, max_new_tokens=1024)
        
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
            print(f"Raw LLM output: {len(data.get('action_items', []))} action items, {len(data.get('decisions', []))} decisions")
            
            # Validate and clean the data
            data = _validate_and_clean_extraction(data)
            print(f"After validation: {len(data.get('action_items', []))} action items, {len(data.get('decisions', []))} decisions")
            
        except json.JSONDecodeError as json_error:
            print(f"Failed to parse JSON from extraction response. Error: {json_error}")
            print(f"Using rule-based extraction as fallback...")
            full_text = " ".join(sentences)
            return _extract_with_rules(full_text)

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

        # If LLM returned insufficient results, combine with rule-based
        if len(actions) < 3 or len(decisions) < 2:
            print(f"LLM results seem incomplete, augmenting with rule-based extraction...")
            full_text = " ".join(sentences)
            rule_actions, rule_decisions = _extract_with_rules(full_text)
            
            # Merge results - add rule-based items that aren't duplicates
            existing_descriptions = {a.description.lower() for a in actions}
            for rule_action in rule_actions:
                if rule_action.description.lower() not in existing_descriptions:
                    actions.append(rule_action)
                    existing_descriptions.add(rule_action.description.lower())
            
            existing_decision_texts = {d.text.lower()[:50] for d in decisions}
            for rule_decision in rule_decisions:
                if rule_decision.text.lower()[:50] not in existing_decision_texts:
                    decisions.append(rule_decision)
                    existing_decision_texts.add(rule_decision.text.lower()[:50])
            
            print(f"After augmentation: {len(actions)} action items, {len(decisions)} decisions")

        return actions, decisions
        
    except Exception as e:
        print(f"Error in extraction: {e}")
        print("Using rule-based extraction as fallback...")
        full_text = " ".join(sentences)
        return _extract_with_rules(full_text)
