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
    
    # Database Settings (PostgreSQL — Supabase/Railway/local via Docker all work).
    # Bare postgres:// or postgresql:// URLs (Supabase/Railway style) are
    # normalized to the psycopg driver in app/database/db.py.
    DATABASE_URL: str = "postgresql+psycopg://lenny:lenny@localhost:5432/lenny_growth"
    
    # ChromaDB Vector Store
    CHROMA_PERSIST_DIRECTORY: str = str(BASE_DIR / "chroma_db")
    CHROMA_COLLECTION_NAME: str = "lenny_growth_transcripts"
    
    # Ingestion Configuration
    TRANSCRIPTS_DIR: str = str(BASE_DIR / "app" / "ingestion" / "transcripts")
    CHUNK_SIZE: int = 600
    CHUNK_OVERLAP: int = 120
    TOP_K_RETRIEVAL: int = 4

    # Refusal gate: a chunk is only used if its bi-encoder cosine similarity
    # (0-1) clears this. On the default bge-small corpus, on-topic queries score
    # 0.66-0.81 while off-topic ones stay under 0.58 — so off-topic questions
    # get a genuine refusal instead of forced nearest-neighbor answers.
    # Calibrated for EMBEDDING_MODEL=BAAI/bge-small-en-v1.5; recalibrate when
    # switching models.
    RELEVANCE_CUTOFF: float = 0.62

    # Embedding + reranking stack (sentence-transformers). When EMBEDDING_MODEL
    # changes, the vector store re-indexes itself automatically on next use.
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBED_QUERY_INSTRUCTION: bool = True
    # Cross-encoder used to ORDER gate-passing chunks (answer-bearing
    # relevance). Admission/refusal is decided by the cosine gate above.
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANK_ENABLED: bool = True
    RERANK_CANDIDATES: int = 12

settings = Settings()
