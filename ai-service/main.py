from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
import traceback
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor

from services.stt import transcribe_audio
from services.clean import clean_transcript
from services.summarization import summarize
from services.diarization import diarize
from services.extraction import extract_actions_and_decisions
from schemas.mom import ActionItem, Decision
from core.config import settings

try:
    from services.vector_db import add_training_example, get_similar_examples, save_vector_db, load_vector_db
except ImportError:
    add_training_example = None
    get_similar_examples = None
    save_vector_db = None
    load_vector_db = None

app = FastAPI(title="AI Service API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Thread pool executor for running CPU-bound tasks in parallel
_executor = ThreadPoolExecutor(max_workers=4)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "AI Service"}

@app.on_event("startup")
async def startup_event():
    """Load vector database on startup"""
    if load_vector_db:
        try:
            load_vector_db()
        except Exception as e:
            print(f"Could not load vector database: {e}")

@app.post("/vector-db/add-example")
async def add_example(
    text: str = Form(...),
    action_items: str = Form(...),  # JSON string
    decisions: str = Form(...)  # JSON string
):
    """Add a training example to the vector database"""
    if not add_training_example:
        raise HTTPException(status_code=501, detail="Vector database not available")
    
    try:
        action_items_list = json.loads(action_items)
        decisions_list = json.loads(decisions)
        
        add_training_example(text, action_items_list, decisions_list)
        save_vector_db()
        
        return {"status": "success", "message": "Training example added"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add example: {str(e)}")

@app.post("/vector-db/search")
async def search_examples(
    text: str = Form(...),
    top_k: Optional[int] = Form(default=None)
):
    """Search for similar examples in vector database"""
    if not get_similar_examples:
        raise HTTPException(status_code=501, detail="Vector database not available")
    
    try:
        examples = get_similar_examples(text, top_k=top_k)
        return {
            "count": len(examples),
            "examples": [
                {
                    "text": ex["text"],
                    "action_items": ex["action_items"],
                    "decisions": ex["decisions"],
                    "similarity_score": ex.get("similarity_score", 0.0)
                }
                for ex in examples
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

@app.post("/vector-db/save")
async def save_db():
    """Save vector database to disk"""
    if not save_vector_db:
        raise HTTPException(status_code=501, detail="Vector database not available")
    
    try:
        save_vector_db()
        return {"status": "success", "message": "Vector database saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")

@app.post("/speech-to-text")
async def speech_to_text(
    audio: UploadFile = File(...),
    language: Optional[str] = Form(default="vi")
):
    """Convert audio file to text using Speechmatics API"""
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / (audio.filename or "audio_input")
            data = await audio.read()
            target.write_bytes(data)
            
            transcript = await transcribe_audio(str(target), language)
            return {"transcript": transcript}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Speech-to-text failed: {str(e)}")

@app.post("/clean")
async def clean_text(
    text: str = Form(...)
):
    """Clean and normalize transcript text"""
    try:
        cleaned = clean_transcript(text)
        return {"cleaned_text": cleaned}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Text cleaning failed: {str(e)}")

@app.post("/summarize")
async def summarize_text(
    text: str = Form(...),
    language: str = Form(default="vi")
):
    """Generate structured meeting minutes from text"""
    try:
        sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
        if not sentences:
            raise HTTPException(status_code=400, detail="No meaningful content found")
        
        structured_summary = summarize(sentences, language)
        return structured_summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Summarization failed: {str(e)}")

@app.post("/diarize")
async def diarize_text(
    text: str = Form(...)
):
    """Perform speaker diarization on text"""
    try:
        segments = diarize(text)
        return {"segments": [{"speaker": speaker, "text": text} for speaker, text in segments]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diarization failed: {str(e)}")

@app.post("/extract")
async def extract_content(
    text: str = Form(...)
):
    """Extract action items and decisions from text"""
    try:
        sentences = [s.strip() for s in text.replace("\n", " ").split(".") if s.strip()]
        if not sentences:
            raise HTTPException(status_code=400, detail="No meaningful content found")
        
        # Try to get diarization data for better extraction
        cleaned = clean_transcript(text)
        segments = diarize(cleaned)
        actions, decisions = extract_actions_and_decisions(sentences, segments)
        
        # Ensure we always return valid lists
        if actions is None:
            actions = []
        if decisions is None:
            decisions = []
        
        return {
            "action_items": [
                {
                    "description": str(action.description) if action.description else "",
                    "owner": action.owner if action.owner else None,
                    "due_date": action.due_date if action.due_date else None,
                    "priority": action.priority if action.priority else None
                } for action in actions
            ],
            "decisions": [
                {
                    "text": str(decision.text) if decision.text else "",
                    "owner": decision.owner if decision.owner else None
                } for decision in decisions
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in extract endpoint: {type(e).__name__}: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

@app.post("/process-full")
async def process_full(
    audio: Optional[UploadFile] = File(default=None),
    transcript: Optional[UploadFile] = File(default=None),
    language: Optional[str] = Form(default="vi")
):
    """Full processing pipeline: STT -> Clean -> (Summarize || Diarize) -> Extract
    
    Optimized to run summarize and diarize in parallel for better performance.
    """
    try:
        raw_text: Optional[str] = None

        # Step 1: Get raw text (STT if audio, or read transcript)
        if audio is not None:
            with tempfile.TemporaryDirectory() as tmpdir:
                target = Path(tmpdir) / (audio.filename or "audio_input")
                data = await audio.read()
                target.write_bytes(data)
                raw_text = await transcribe_audio(str(target), language)
        elif transcript is not None:
            data = await transcript.read()
            raw_text = data.decode("utf-8", errors="ignore")
        else:
            raise HTTPException(status_code=400, detail="No input file provided")

        if not raw_text or not raw_text.strip():
            raise HTTPException(status_code=400, detail="No content found in the uploaded file")

        # Step 2: Clean text (must be done first)
        cleaned = await asyncio.to_thread(clean_transcript, raw_text)
        sentences = [s.strip() for s in cleaned.replace("\n", " ").split(".") if s.strip()]
        
        if not sentences:
            raise HTTPException(status_code=400, detail="No meaningful content found after processing")
        
        # Step 3: Run summarize and diarize in parallel (they are independent)
        # Both can run simultaneously since they don't depend on each other
        structured_summary_task = asyncio.to_thread(summarize, sentences, language)
        segments_task = asyncio.to_thread(diarize, cleaned)
        
        # Wait for both to complete
        structured_summary, segments = await asyncio.gather(
            structured_summary_task,
            segments_task,
            return_exceptions=True
        )
        
        # Handle exceptions from parallel tasks - raise if critical errors occur
        if isinstance(structured_summary, Exception):
            print(f"Summarize error: {structured_summary}")
            # Summarize is important, but we can continue with empty summary
            structured_summary = {}
        if isinstance(segments, Exception):
            print(f"Diarize error: {segments}")
            # Diarization is optional for extraction, can continue with empty segments
            segments = []
        
        # Ensure valid types (same as original code)
        if segments is None:
            segments = []
        if structured_summary is None:
            structured_summary = {}
        
        # Step 4: Extract action items and decisions (depends on diarization)
        actions, decisions = await asyncio.to_thread(
            extract_actions_and_decisions, 
            sentences, 
            segments
        )
        
        # Ensure we always return valid lists
        if actions is None:
            actions = []
        if decisions is None:
            decisions = []

        return {
            "transcript": cleaned,
            "structured_summary": structured_summary if structured_summary else {},
            "action_items": [
                {
                    "description": str(action.description) if action.description else "",
                    "owner": action.owner if action.owner else None,
                    "due_date": action.due_date if action.due_date else None,
                    "priority": action.priority if action.priority else None
                } for action in actions
            ],
            "decisions": [
                {
                    "text": str(decision.text) if decision.text else "",
                    "owner": decision.owner if decision.owner else None
                } for decision in decisions
            ],
            "diarization": [{"speaker": str(speaker), "text": str(text)} for speaker, text in segments]
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error in process_full: {type(e).__name__}: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    """Global exception handler to ensure CORS headers are always sent"""
    print(f"Global exception handler caught: {type(exc).__name__}: {str(exc)}")
    print(f"Traceback: {traceback.format_exc()}")
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"Internal server error: {str(exc)}",
            "type": type(exc).__name__
        },
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="localhost", port=8001)