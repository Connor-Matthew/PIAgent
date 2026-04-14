from pydantic import SecretStr
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./piagent.db"
    audio_dir: str = "./audio_files"
    openai_api_key: SecretStr = ""
    anthropic_api_key: SecretStr = ""
    google_api_key: SecretStr = ""
    deepseek_api_key: SecretStr = ""
    fish_audio_api_key: SecretStr = ""
    chroma_dir: str = "./chroma_data"
    upload_dir: str = "./uploads"
    cors_origins: list[str] = ["http://localhost:5173"]

    class Config:
        env_file = ".env"

settings = Settings()
