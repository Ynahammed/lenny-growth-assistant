import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "Lenny Growth Assistant"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    
    # LLM Provider Configuration ('ollama' | 'groq' | 'gemini' | 'mock')
    LLM_PROVIDER: str = "ollama"
    
    # Ollama Settings (Local)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"
    
    # Groq Settings (Ultra-Fast Cloud Llama)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    
    # Google Gemini Settings
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.6-flash"
    
    # Database Settings (Local SQLite)
    DATABASE_URL: str = f"sqlite:///{BASE_DIR}/lenny_growth.db"
    
    # ChromaDB Vector Store
    CHROMA_PERSIST_DIRECTORY: str = str(BASE_DIR / "chroma_db")
    CHROMA_COLLECTION_NAME: str = "lenny_growth_transcripts"
    
    # Ingestion Configuration
    TRANSCRIPTS_DIR: str = str(BASE_DIR / "app" / "ingestion" / "transcripts")
    CHUNK_SIZE: int = 600
    CHUNK_OVERLAP: int = 120
    TOP_K_RETRIEVAL: int = 4

settings = Settings()
