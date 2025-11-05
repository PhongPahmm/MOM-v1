from typing import Optional
import os

try:
    import whisper
except ImportError:
    whisper = None

from core.config import settings

# Global model cache
_whisper_model = None

def _get_whisper_model():
    """Lazy load Whisper model to avoid loading on import"""
    global _whisper_model
    if _whisper_model is None:
        if whisper is None:
            raise ImportError(
                "Whisper is not installed. Please install it with: pip install openai-whisper"
            )
        
        model_size = settings.whisper_model_size or "base"
        print(f"Loading Whisper model ({model_size})... This may take a while on first run.")
        _whisper_model = whisper.load_model(model_size)
        print(f"Whisper model loaded successfully.")
    
    return _whisper_model

async def transcribe_audio(file_path: str, language: Optional[str] = None) -> str:
    """
    Transcribe audio file using Whisper (local model).
    """
    if not os.path.exists(file_path):
        raise ValueError(f"Audio file not found: {file_path}")

    try:
        model = _get_whisper_model()
        
        # Map language code
        whisper_lang = language or "en"
        if whisper_lang == "vi":
            whisper_lang = "vi"
        
        # Transcribe audio
        print(f"Transcribing audio file: {file_path}")
        result = model.transcribe(
            file_path,
            language=whisper_lang if whisper_lang != "auto" else None,
            fp16=False  # Set to False for CPU, True for GPU
        )
        
        transcript = result.get("text", "").strip()
        
        if not transcript:
            raise ValueError("Transcription resulted in empty text")
        
        print(f"Transcription completed. Length: {len(transcript)} characters")
        return transcript

    except Exception as e:
        raise ValueError(f"Whisper transcription failed: {e}")
