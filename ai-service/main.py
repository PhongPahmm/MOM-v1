from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
import traceback

from services.stt import transcribe_audio
from services.clean import clean_transcript
from services.summarization import summarize
from services.diarization import diarize
from services.extraction import extract_actions_and_decisions
from schemas.mom import ActionItem, Decision
from core.config import settings

app = FastAPI(title="AI Service API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "AI Service"}

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
        
        return {
            "action_items": [
                {
                    "description": action.description,
                    "owner": action.owner,
                    "due_date": action.due_date,
                    "priority": action.priority
                } for action in actions
            ],
            "decisions": [
                {
                    "text": decision.text,
                    "owner": decision.owner
                } for decision in decisions
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")

@app.post("/process-full")
async def process_full(
    audio: Optional[UploadFile] = File(default=None),
    transcript: Optional[UploadFile] = File(default=None),
    language: Optional[str] = Form(default="vi")
):
    """Full processing pipeline: STT -> Clean -> Summarize -> Extract"""
    try:
        raw_text: Optional[str] = None

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

        # Clean text
        cleaned = clean_transcript(raw_text)
        sentences = [s.strip() for s in cleaned.replace("\n", " ").split(".") if s.strip()]
        
        if not sentences:
            raise HTTPException(status_code=400, detail="No meaningful content found after processing")
        
        # Get structured summary data
        structured_summary = summarize(sentences, language)
        segments = diarize(cleaned)
        actions, decisions = extract_actions_and_decisions(sentences, segments)

        return {
            "transcript": cleaned,
            "structured_summary": structured_summary,
            "action_items": [
                {
                    "description": action.description,
                    "owner": action.owner,
                    "due_date": action.due_date,
                    "priority": action.priority
                } for action in actions
            ],
            "decisions": [
                {
                    "text": decision.text,
                    "owner": decision.owner
                } for decision in decisions
            ],
            "diarization": [{"speaker": speaker, "text": text} for speaker, text in segments]
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
