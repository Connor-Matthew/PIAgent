from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./piagent.db"
    audio_dir: str = "./audio_files"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    google_api_key: str = ""
    deepseek_api_key: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
