"""
Script để generate dataset từ transcripts và lưu vào file JSONL
Chỉ sử dụng local LLM model
"""
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.extraction import _generate_with_llm
from core.config import settings

# System prompt để extract structured data
SYSTEM_PROMPT = """You are a data extractor that converts meeting transcripts into structured JSON.
Follow this schema strictly:

{
  "transcript": "",
  "structured_summary": {
    "title": "Realtime Meeting",
    "date": "",
    "time": "",
    "attendants": [],
    "project_name": "",
    "customer": "",
    "table_of_content": [],
    "main_content": ""
  },
  "action_items": [
    {
      "description": "",
      "owner": "",
      "due_date": "",
      "priority": ""
    }
  ],
  "decisions": [
    {
      "text": "",
      "owner": ""
    }
  ],
  "diarization": [
    {
      "speaker": "",
      "text": ""
    }
  ]
}

Return valid JSON only — no explanations."""

# Sample transcripts để generate dataset
SAMPLE_TRANSCRIPTS = [
    """Good morning everyone. HR will draft the remote work policy by October 15.
Finance needs to finalize the Q4 budget by October 20.
Sarah to coordinate with external vendors by end of week.""",
    
    """John confirmed the marketing team will deliver the new campaign plan next Tuesday.
Lisa will prepare the slides for the client meeting.
The group decided to extend the testing phase by one week.""",
    
    """We decided to implement a 3-day remote work policy starting Q1 2024.
The board approved a 10% budget increase for development.
Team agreed to adopt agile methodology for the project.""",
    
    """HR will draft the policy by October 15 and send it to legal for review.
Finance needs to prepare the budget report and submit it to the board by October 20.""",
    
    """Huy will coordinate with ops to make sure traffic is rerouted before midnight.
Minh needs to adjust the keepalive timeout to 75 seconds and test again.
Ngan will configure grafana alerts and slack notifications before 10 pm tonight.""",
    
    """We decided to reschedule the redis migration for november 15, 2025.
The team agreed to proceed with the migration plan.
We decided to do a dry run at 10 pm tonight.""",
    
    """The proposal is to introduce flexible working hours.
Managers must schedule weekly check-ins starting November 1.
We agreed to use output-based performance metrics instead of time tracking.""",
    
    """Engineering must deploy the staging environment by friday.
Marketing is responsible for the content strategy.
John will review the wireframes and provide feedback.""",
    
    """IT will implement the new VPN solution by next tuesday.
The proposal is to introduce flexible working hours.
We decided to use output-based performance metrics.""",
    
    """Managers should schedule weekly check-ins starting november 1.
IT to implement the new VPN solution by next tuesday.
We agreed to adopt agile methodology for this project."""
]

def generate_with_local_llm(transcript: str) -> str:
    """Generate structured output using local LLM"""
    # Build prompt optimized for local LLM
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"Transcript:\n{transcript}\n\n"
        "Extract action items and decisions from the transcript above. "
        "Return ONLY valid JSON following the schema. No markdown, no explanations, just JSON:"
    )
    
    try:
        print("  Generating with local LLM...")
        output = _generate_with_llm(prompt, max_new_tokens=2048)
        
        # Clean output
        output = output.strip()
        
        # Remove markdown if present
        if "```json" in output:
            output = output.split("```json")[1].split("```")[0].strip()
        elif "```" in output:
            output = output.split("```")[1].split("```")[0].strip()
        
        return output
    except OSError as e:
        if "gated repo" in str(e) or "401" in str(e) or "access" in str(e).lower():
            print(f"\n❌ Authentication Error:")
            print(f"   Model '{settings.llm_model_name}' requires HuggingFace authentication.")
            print(f"\n   To fix:")
            print(f"   1. Login: huggingface-cli login")
            print(f"   2. Or set token: export HF_TOKEN=your_token")
            print(f"   3. Request access: https://huggingface.co/{settings.llm_model_name}")
            print(f"   4. Or change model in .env: LLM_MODEL_NAME=other-model-name")
        else:
            print(f"  Error with local LLM: {e}")
        return None
    except Exception as e:
        print(f"  Error with local LLM: {e}")
        import traceback
        traceback.print_exc()
        return None

def generate_dataset(
    transcripts: list = None,
    output_file: str = "meeting_dataset.jsonl"
):
    """
    Generate dataset từ transcripts sử dụng local LLM
    
    Args:
        transcripts: List of transcript strings (default: SAMPLE_TRANSCRIPTS)
        output_file: Output file path
    """
    if transcripts is None:
        transcripts = SAMPLE_TRANSCRIPTS
    
    print(f"📝 Generating dataset from {len(transcripts)} transcripts...")
    print(f"💾 Output file: {output_file}")
    print(f"🤖 Using local LLM model: {settings.llm_model_name}")
    print(f"   (Model location: {settings.llm_model_name})")
    
    successful = 0
    failed = 0
    
    with open(output_file, "w", encoding="utf-8") as f:
        for i, transcript in enumerate(transcripts, start=1):
            print(f"\n⏳ Processing transcript {i}/{len(transcripts)}...")
            
            try:
                structured_output = generate_with_local_llm(transcript)
                if structured_output:
                    print(f"  ✅ Generated with local LLM")
                else:
                    print(f"  ❌ Failed to generate output")
                    failed += 1
                    continue
            except Exception as e:
                print(f"  ❌ Local LLM failed: {e}")
                failed += 1
                continue
            
            if structured_output is None:
                print(f"  ❌ Failed to generate output for transcript {i}")
                failed += 1
                continue
            
            # Validate JSON
            try:
                # Try to extract JSON if wrapped in markdown
                json_text = structured_output
                if "```json" in json_text:
                    json_text = json_text.split("```json")[1].split("```")[0].strip()
                elif "```" in json_text:
                    json_text = json_text.split("```")[1].split("```")[0].strip()
                
                # Validate it's valid JSON
                parsed = json.loads(json_text)
                
                # Create record for fine-tuning format
                record = {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": transcript},
                        {"role": "assistant", "content": json_text}
                    ]
                }
                
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                print(f"  ✅ Successfully processed transcript {i}")
                successful += 1
                
            except json.JSONDecodeError as e:
                print(f"  ❌ Invalid JSON for transcript {i}: {e}")
                print(f"  Raw output: {structured_output[:200]}...")
                failed += 1
    
    print(f"\n✅ Dataset generation complete!")
    print(f"   Successful: {successful}/{len(transcripts)}")
    print(f"   Failed: {failed}/{len(transcripts)}")
    print(f"   File saved: {output_file}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate dataset from transcripts using local LLM model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate dataset with local LLM
  python scripts/generate_dataset.py --output dataset.jsonl
  
  # Load transcripts from file
  python scripts/generate_dataset.py --transcripts-file transcripts.txt --output dataset.jsonl
        """
    )
    parser.add_argument("--output", "-o", default="meeting_dataset.jsonl", help="Output file path")
    parser.add_argument("--transcripts-file", help="File containing transcripts (one per line or JSON array)")
    
    args = parser.parse_args()
    
    # Load transcripts from file if provided
    transcripts = None
    if args.transcripts_file:
        with open(args.transcripts_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content.startswith("["):
                # JSON array
                transcripts = json.loads(content)
            else:
                # One per line
                transcripts = [line.strip() for line in content.split("\n") if line.strip()]
    
    # Use local LLM only
    generate_dataset(
        transcripts=transcripts,
        output_file=args.output
    )

