from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "AI Service"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8001
    
    # Local Model Settings
    # Whisper model size - sử dụng tiny để tiết kiệm tài nguyên
    whisper_model_size: str = "base"  # Options: tiny, base, small, medium, large
    
    # Embedding Model for Vector-based Extraction (optional)
    # Options: "sentence-transformers/all-MiniLM-L6-v2" (fast, lightweight)
    #          "sentence-transformers/all-mpnet-base-v2" (better quality, slower)
    #          "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2" (multilingual)
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    
    # Vector Database Settings
    use_vector_extraction: bool = True  # Use vector-based extraction instead of prompt
    vector_similarity_threshold: float = 0.7  # Minimum similarity score for retrieval
    top_k_examples: int = 5  # Number of similar examples to retrieve
    
    # API Keys
    # OpenAI API Key - ưu tiên sử dụng, nếu hết hạn sẽ fallback sang Gemini
    openai_api_key: Optional[str] = None  # Đọc từ env variable OPENAI_API_KEY
    # Google API Key - fallback khi OpenAI API hết hạn
    google_api_key: Optional[str] = None  # Đọc từ env variable GOOGLE_API_KEY (cho Gemini)
    google_cloud_credentials_path: Optional[str] = None
    speechmatics_api_key: Optional[str] = None

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }

settings = Settings()
