"""
Script để load dataset từ JSONL file và thêm vào vector database
"""
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.vector_db import add_training_example, save_vector_db, _build_vector_index
from core.config import settings

def load_dataset_to_vector_db(dataset_file: str = "meeting_dataset.jsonl"):
    """
    Load dataset từ JSONL file và thêm vào vector database
    
    Args:
        dataset_file: Path to JSONL dataset file
    """
    print(f"📖 Loading dataset from: {dataset_file}")
    
    if not Path(dataset_file).exists():
        print(f"❌ File not found: {dataset_file}")
        return
    
    examples_added = 0
    examples_skipped = 0
    
    with open(dataset_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            
            try:
                record = json.loads(line)
                
                # Extract data from fine-tuning format
                messages = record.get("messages", [])
                if len(messages) < 3:
                    print(f"  ⚠️  Line {line_num}: Invalid format (need system, user, assistant)")
                    examples_skipped += 1
                    continue
                
                # Get transcript (user message)
                transcript = None
                for msg in messages:
                    if msg.get("role") == "user":
                        transcript = msg.get("content", "")
                        break
                
                if not transcript:
                    print(f"  ⚠️  Line {line_num}: No user message found")
                    examples_skipped += 1
                    continue
                
                # Get structured output (assistant message)
                structured_output = None
                for msg in messages:
                    if msg.get("role") == "assistant":
                        structured_output = msg.get("content", "")
                        break
                
                if not structured_output:
                    print(f"  ⚠️  Line {line_num}: No assistant message found")
                    examples_skipped += 1
                    continue
                
                # Parse JSON from assistant message
                try:
                    # Try to extract JSON if wrapped in markdown
                    json_text = structured_output
                    if "```json" in json_text:
                        json_text = json_text.split("```json")[1].split("```")[0].strip()
                    elif "```" in json_text:
                        json_text = json_text.split("```")[1].split("```")[0].strip()
                    
                    data = json.loads(json_text)
                    
                    # Extract action items and decisions
                    action_items = data.get("action_items", [])
                    decisions = data.get("decisions", [])
                    
                    # Add to vector database
                    add_training_example(transcript, action_items, decisions)
                    examples_added += 1
                    print(f"  ✅ Line {line_num}: Added example ({len(action_items)} actions, {len(decisions)} decisions)")
                    
                except json.JSONDecodeError as e:
                    print(f"  ❌ Line {line_num}: Invalid JSON in assistant message: {e}")
                    examples_skipped += 1
                
            except json.JSONDecodeError as e:
                print(f"  ❌ Line {line_num}: Invalid JSON: {e}")
                examples_skipped += 1
            except Exception as e:
                print(f"  ❌ Line {line_num}: Error: {e}")
                examples_skipped += 1
    
    # Rebuild vector index
    print("\n🔨 Rebuilding vector index...")
    _build_vector_index()
    
    # Save vector database
    print("💾 Saving vector database...")
    save_vector_db()
    
    print(f"\n✅ Dataset loading complete!")
    print(f"   Examples added: {examples_added}")
    print(f"   Examples skipped: {examples_skipped}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Load dataset to vector database")
    parser.add_argument("--dataset", "-d", default="meeting_dataset.jsonl", help="Dataset JSONL file path")
    
    args = parser.parse_args()
    
    load_dataset_to_vector_db(args.dataset)

