from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "AI Service"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8001
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
