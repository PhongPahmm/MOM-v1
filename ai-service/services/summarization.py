from typing import List, Dict, Any
import json
import time
import re

try:
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import torch
except ImportError:
    AutoTokenizer = None
    AutoModelForCausalLM = None
    torch = None

from core.config import settings

# Global model cache
_llm_model = None
_llm_tokenizer = None

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

def _generate_with_llm(prompt: str, max_new_tokens: int = 2048) -> str:
    """Generate text using local LLM with optimized parameters for accuracy"""
    model, tokenizer = _get_llm_model()
    
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=6144)
    
    if torch.cuda.is_available():
        inputs = {k: v.to("cuda") for k, v in inputs.items()}
    
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=0.3,  # Lower temperature for more accurate output
            do_sample=True,
            top_p=0.85,
            top_k=40,
            repetition_penalty=1.1,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id
        )
    
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)
    
    # Remove the input prompt from response
    if response.startswith(prompt):
        response = response[len(prompt):].strip()
    
    return response

def summarize(sentences: List[str], language: str = "vi") -> Dict[str, Any]:
    """
    Generate structured meeting minutes from sentences using local LLM
    Returns a dictionary with structured content
    """
    if AutoTokenizer is None or AutoModelForCausalLM is None:
        print(
            "Warning: Transformers library is not installed. "
            "Please install it with: pip install transformers torch"
        )
        return _get_default_structured_content(sentences)

    try:
        prompt = (
            f"Language: {language}. "
            + _SYSTEM_PROMPT
            + "\n\nContent:\n"
            + "\n".join(sentences)
            + "\n\nRespond with ONLY valid JSON, no other text:"
        )
        
        print("Generating meeting minutes with local LLM...")
        text = _generate_with_llm(prompt, max_new_tokens=2048)
        
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
                import re
                json_match = re.search(r'\{.*\}', cleaned_text, re.DOTALL)
                if json_match:
                    cleaned_text = json_match.group(0)
                
                structured_data = json.loads(cleaned_text)
                print("Successfully parsed meeting minutes JSON")
                return structured_data
            except json.JSONDecodeError as e:
                print(f"Failed to parse JSON response: {e}")
                return _get_fallback_structured_content(text, sentences)
        
        return _get_default_structured_content(sentences)
        
    except Exception as e:
        print(f"Error in summarization: {e}")
        return _get_default_structured_content(sentences)

def _extract_with_rules(text: str) -> Dict[str, Any]:
    """Rule-based extraction as fallback"""
    # Extract title from first meaningful sentence
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    title = "Meeting Minutes"
    if sentences:
        first_sentence = sentences[0][:150]
        if "policy review" in first_sentence.lower():
            title = "Policy Review Meeting"
        elif "remote work" in first_sentence.lower() or "hybrid work" in first_sentence.lower():
            title = "Remote Work Policy Meeting"
        elif "project" in first_sentence.lower():
            title = "Project Discussion Meeting"
        elif "team" in first_sentence.lower():
            title = "Team Meeting"
        elif "meeting" in first_sentence.lower():
            # Extract the topic before "meeting"
            match = re.search(r'(\w+(?:\s+\w+){0,3})\s+meeting', first_sentence, re.IGNORECASE)
            if match:
                title = match.group(0).title()
        else:
            # Use meaningful words from purpose
            purpose_match = re.search(r'purpose.*?is to\s+(.{10,60}?)(?:\.|$)', text, re.IGNORECASE)
            if purpose_match:
                purpose = purpose_match.group(1).strip()
                title = purpose[:50].title() + " - Meeting"
    
    # Extract dates and times
    date_patterns = [
        r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
        r'\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}\b',
        r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2},?\s+\d{4}\b'
    ]
    date_found = "To be determined"
    for pattern in date_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            date_found = match.group(0)
            break
    
    time_patterns = [
        r'\b\d{1,2}:\d{2}\s*(?:am|pm|AM|PM)\b',
        r'\b\d{1,2}\s*(?:am|pm|AM|PM)\b'
    ]
    time_found = "To be determined"
    for pattern in time_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            time_found = match.group(0)
            break
    
    # Extract attendants - be more selective
    attendants = []
    # Look for proper names with context (not just any capitalized words)
    name_patterns = [
        r'\b(?:Mr|Ms|Mrs|Dr|Professor)\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b',
    ]
    
    for pattern in name_patterns:
        matches = re.findall(pattern, text)
        attendants.extend(matches)
    
    # Also look for names in specific contexts
    context_patterns = [
        r'(?:presented by|led by|facilitated by|with)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)',
        r'([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:will|presented|discussed|mentioned)'
    ]
    
    for pattern in context_patterns:
        matches = re.findall(pattern, text)
        attendants.extend(matches[:5])
    
    # Remove duplicates and common false positives
    attendants = list(set(attendants))
    # Filter out department names and common false positives
    false_positives = ['Good Morning', 'Thank You', 'In Response', 'To Solve', 'Action Items', 
                      'Before Closing', 'Next Review', 'Remote Work', 'Many Employees']
    attendants = [a for a in attendants if a not in false_positives and len(a) < 30]
    attendants = attendants[:10]  # Limit to 10
    
    # Extract project name - only if explicitly mentioned
    project_name = "To be determined"
    project_patterns = [
        r'(?:project|initiative|program)\s+(?:called|named|titled)\s+["\']?([A-Z][A-Za-z0-9\s]+?)["\']?(?:\s|\.|\,)',
        r'(?:the|a)\s+([A-Z][A-Za-z0-9\s]{3,30}?)\s+project',
    ]
    for pattern in project_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            candidate = match.group(1).strip()
            # Validate it's not a verb or common word
            if not any(word in candidate.lower() for word in ['will', 'should', 'must', 'can', 'the', 'a', 'an']):
                project_name = candidate
                break
    
    # Extract customer - only if explicitly mentioned
    customer = "To be determined"
    customer_patterns = [
        r'(?:client|customer)\s+(?:is|called|named)\s+["\']?([A-Z][A-Za-z0-9\s&]+?)["\']?(?:\s|\.|\,)',
        r'(?:for|with)\s+(?:client|customer)\s+([A-Z][A-Za-z][A-Za-z0-9\s&]+)',
    ]
    for pattern in customer_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            customer = match.group(1).strip()[:50]
            break
    
    # Generate table of contents from key topics found in text
    topics = []
    topic_mapping = {
        'policy': 'Policy Framework',
        'guideline': 'Guidelines',
        'remote work': 'Remote Work',
        'flexibility': 'Work Flexibility',
        'collaboration': 'Team Collaboration',
        'well-being': 'Employee Well-being',
        'equipment': 'Equipment & Tools',
        'productivity': 'Productivity Measurement',
        'communication': 'Communication',
        'security': 'Security & Compliance',
        'culture': 'Company Culture',
        'implementation': 'Implementation Plan',
        'action items': 'Action Items',
        'feedback': 'Feedback',
        'budget': 'Budget'
    }
    
    for keyword, topic_name in topic_mapping.items():
        if keyword.lower() in text.lower():
            topics.append(topic_name)
    
    if not topics:
        # Default structure
        topics = ["Introduction", "Discussion", "Decisions", "Action Items", "Conclusion"]
    
    # Create main content summary with better structure
    # Split by major sections
    summary_parts = []
    
    # Introduction (first 100 words)
    words = text.split()
    if len(words) > 100:
        summary_parts.append(" ".join(words[:100]))
    
    # Key decisions
    decision_section = re.search(
        r'((?:proposal is|decided to|agreed to|consensus was).{50,300}?)(?:\.|(?=[A-Z]))',
        text,
        re.IGNORECASE
    )
    if decision_section:
        summary_parts.append("Key Decision: " + decision_section.group(1).strip())
    
    # Action items summary
    action_section = re.search(
        r'Action items were assigned\.(.*?)(?:Before closing|The next|$)',
        text,
        re.IGNORECASE | re.DOTALL
    )
    if action_section:
        action_text = action_section.group(1).strip()
        action_words = action_text.split()[:100]
        summary_parts.append("Action Items: " + " ".join(action_words))
    
    main_content = " ".join(summary_parts) if summary_parts else " ".join(words[:500])
    
    return {
        "title": title,
        "date": date_found,
        "time": time_found,
        "attendants": attendants,
        "project_name": project_name,
        "customer": customer,
        "table_of_content": topics[:12],
        "main_content": main_content
    }

def _get_default_structured_content(sentences: List[str]) -> Dict[str, Any]:
    """Fallback structured content when AI is not available"""
    full_text = " ".join(sentences)
    return _extract_with_rules(full_text)

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
