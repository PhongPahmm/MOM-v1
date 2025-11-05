from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "AI Service"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8001
    
    # Local Model Settings
    whisper_model_size: str = "small"  # Options: tiny, base, small, medium, large
    
    # LLM Model Options (choose based on your hardware):
    # - "google/gemma-2b-it": Lightweight, works on CPU, faster but less accurate
    # - "mistralai/Mistral-7B-Instruct-v0.2": Better quality, needs more RAM (recommended)
    # - "meta-llama/Llama-2-7b-chat-hf": Good alternative, needs HuggingFace token
    # - "TheBloke/Mistral-7B-Instruct-v0.2-GGUF": Quantized version, good balance
    llm_model_name: str = "mistralai/Mistral-7B-Instruct-v0.2"
    
    # Use rule-based extraction as fallback when LLM fails
    use_rule_based_fallback: bool = True
    
    # Legacy API keys (not used anymore, kept for backward compatibility)
    openai_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    google_cloud_credentials_path: Optional[str] = None
    speechmatics_api_key: Optional[str] = None

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

settings = Settings()
